# agentt/linear_client.py
"""
Thin wrapper around the Linear GraphQL API.
Handles issue creation and webhook signature verification.
"""

import os
import hmac
import hashlib
import requests
from dotenv import load_dotenv

load_dotenv()

LINEAR_API_URL = "https://api.linear.app/graphql"
LINEAR_API_KEY = os.getenv("LINEAR_API_KEY", "")
LINEAR_TEAM_ID = os.getenv("LINEAR_TEAM_ID", "")


def _risk_to_priority(risk_score: int) -> int:
    """
    Maps ITSM risk score (0–100) to Linear priority integer.
      1 = Urgent  → risk >= 61
      2 = High    → risk 31–60
      3 = Medium  → risk 0–30
    """
    if risk_score >= 61:
        return 1  # Urgent
    elif risk_score >= 31:
        return 2  # High
    else:
        return 3  # Medium


def create_issue(title: str, description: str, risk_score: int) -> dict:
    """
    Creates a Linear issue in the configured ITSM team.

    Args:
        title:       Short issue title (e.g. 'INC-2026-A1B2: payment-api timeout')
        description: Markdown body — recovery plan + agent notes + evidence summary.
        risk_score:  Integer 0–100; determines Linear priority.

    Returns:
        dict with keys: 'id' (UUID), 'identifier' (e.g. 'ENG-142'), 'url'.

    Raises:
        RuntimeError: if API key / team ID not set, or if Linear returns an error.
    """
    if not LINEAR_API_KEY:
        raise RuntimeError("LINEAR_API_KEY is not set in .env")
    if not LINEAR_TEAM_ID:
        raise RuntimeError("LINEAR_TEAM_ID is not set in .env")

    priority = _risk_to_priority(risk_score)

    # ── Sanitize inputs ────────────────────────────────────────────────────────
    # Linear title: max 255 characters
    safe_title = title[:255] if len(title) > 255 else title

    # Linear description: enforced limit of 10 000 chars to avoid INVALID_INPUT.
    # Strip any null bytes that could cause validation failures.
    safe_description = description.replace("\x00", "")
    if len(safe_description) > 10_000:
        safe_description = (
            safe_description[:9_900]
            + "\n\n---\n*[Description truncated to fit Linear's limit]*"
        )

    # ── GraphQL mutation ───────────────────────────────────────────────────────
    # Priority is injected directly as a literal integer (avoids variable
    # type-declaration mismatches between client and server GraphQL schemas).
    mutation = f"""
    mutation CreateIssue(
        $title: String!,
        $teamId: String!,
        $description: String
    ) {{
      issueCreate(input: {{
        title:       $title
        teamId:      $teamId
        description: $description
        priority:    {priority}
      }}) {{
        success
        issue {{
          id
          identifier
          url
        }}
      }}
    }}
    """

    variables = {
        "title":       safe_title,
        "teamId":      LINEAR_TEAM_ID,
        "description": safe_description,
    }

    response = requests.post(
        LINEAR_API_URL,
        json={"query": mutation, "variables": variables},
        headers={
            "Authorization": LINEAR_API_KEY,
            "Content-Type":  "application/json",
        },
        timeout=15,
    )
    response.raise_for_status()

    data = response.json()
    errors = data.get("errors")
    if errors:
        # Surface the full validation detail so it's easy to debug
        detail_parts = []
        for err in errors:
            msg  = err.get("message", "?")
            code = (err.get("extensions") or {}).get("code", "")
            val_errors = (err.get("extensions") or {}).get("validationErrors", [])
            if val_errors:
                for ve in val_errors:
                    prop        = ve.get("property", "?")
                    constraints = ve.get("constraints", {})
                    detail_parts.append(
                        f"{msg} [{code}] — field='{prop}' constraints={constraints}"
                    )
            else:
                detail_parts.append(f"{msg} [{code}]")
        raise RuntimeError("Linear API error: " + " | ".join(detail_parts))

    result = data["data"]["issueCreate"]
    if not result.get("success"):
        raise RuntimeError("Linear issueCreate returned success=false")

    issue = result["issue"]
    return {
        "id":         issue["id"],
        "identifier": issue["identifier"],
        "url":        issue["url"],
    }



def verify_webhook_signature(payload_bytes: bytes, signature_header: str, secret: str) -> bool:
    """
    Verifies the Linear-Signature HMAC-SHA256 header.

    Args:
        payload_bytes:     Raw request body bytes.
        signature_header:  Value of the 'Linear-Signature' header.
        secret:            LINEAR_WEBHOOK_SECRET from .env.

    Returns:
        True if the signature is valid, False otherwise.
    """
    if not secret or not signature_header:
        return False

    expected = hmac.new(
        secret.encode("utf-8"),
        payload_bytes,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected, signature_header)
