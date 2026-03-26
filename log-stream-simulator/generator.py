"""
LLM-powered Log Generator for ITSM Agent Testing
====================================================
Uses Gemini to generate a single, realistic, graph-aware incident log batch.
The LLM autonomously:
  1. Reads the Neo4j graph topology.
  2. Picks an application and a tricky incident scenario.
  3. Generates correlated, multi-layer logs (app, db, infra, monitoring).
  4. Stops at the PEAK of the incident (no recovery logs).

Output: generated_logs/raw_batch_<incident_id>.json
  A flat, sorted list of raw log events ready to be consumed by the streamer.
"""

import os
import json
import uuid
import re
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel, Field
from dotenv import load_dotenv
import google.generativeai as genai

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
load_dotenv(dotenv_path=Path(__file__).parent.parent / "agent" / ".env")

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GRAPH_CYPHER_PATH = Path(__file__).parent.parent / "agent" / "seed_graph.cypher"
OUTPUT_DIR = Path(__file__).parent / "generated_logs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

genai.configure(api_key=GEMINI_API_KEY)

# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------

class RawLogEntry(BaseModel):
    """A single log event from any layer of the system."""
    timestamp: str = Field(
        description="ISO 8601 timestamp in UTC, e.g. '2026-03-26T10:01:05Z'"
    )
    level: str = Field(
        description="Log level: INFO, WARN, ERROR, FATAL, or ALERT (for monitoring)"
    )
    layer: str = Field(
        description="Source layer of the log: 'app', 'database', 'infrastructure', or 'monitoring'"
    )
    service_id: str = Field(
        description=(
            "The exact node ID from the graph topology "
            "(e.g. 'payment-api', 'payment-db', 'api-gateway-prod', 'redis-cache')"
        )
    )
    message: str = Field(
        description="The log message. Be realistic and specific — include real error names, connection limits, latencies, etc."
    )
    metadata: dict = Field(
        default_factory=dict,
        description=(
            "Optional key-value metadata. For errors, include things like "
            "request_id, latency_ms, active_connections, max_connections, error_code, etc."
        )
    )


class GeneratedBatch(BaseModel):
    """The full structured output from the LLM."""
    app_id: str = Field(description="The application ID (e.g., 'ecommerce-prod') this incident belongs to.")
    incident_id: str = Field(description="A unique incident ID in the format INC-YYYY-XXXX")
    scenario_title: str = Field(description="A short, human-readable title for this scenario.")
    scenario_description: str = Field(description="A brief (2-3 sentence) description of the incident storyline and what makes it tricky.")
    logs: list[RawLogEntry] = Field(
        description=(
            "The flat, chronologically-sorted list of ALL log events across all layers. "
            "Include 40-80 events. Start with ~10 normal/INFO logs, then gradually degrade, "
            "ending at the absolute peak of the incident (max errors, service degraded/down). "
            "DO NOT include any recovery, normalization, or healing logs."
        )
    )


# ---------------------------------------------------------------------------
# Graph Topology Loader
# ---------------------------------------------------------------------------

def load_graph_topology() -> str:
    """Reads the seed_graph.cypher file as raw text to provide to the LLM."""
    if not GRAPH_CYPHER_PATH.exists():
        raise FileNotFoundError(f"Graph file not found at: {GRAPH_CYPHER_PATH}")
    return GRAPH_CYPHER_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Gemini Prompt & Generation
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are an expert Site Reliability Engineer and log simulation specialist.
You will be given the full topology of a production system described as a Neo4j Cypher script.
Your job is to generate a single, realistic, production-grade incident log batch for testing an AI-powered ITSM agent.

### STRICT RULES:
1.  **Graph Alignment**: All `service_id` values in the logs MUST match a node `id` from the graph topology (Services, Databases, or Infrastructure nodes). Never invent node IDs.
2.  **Incident Storyline**: Choose ONE specific incident. Make it tricky — cascading failures, blast radius across shared resources, misleading symptoms, etc.
3.  **Multi-Layer Correlation**: The incident must be visible across multiple log layers (app, database, infrastructure, monitoring). Events must be temporally correlated (database error causes app error a few seconds later, then a monitoring alert fires).
4.  **No Recovery**: The log sequence MUST stop at the peak of the incident. Do NOT generate any logs showing recovery, normalization, "connections restored", "service restarted successfully", or any healing signals.
5.  **Realistic Log Content**: Use realistic, specific error messages (PostgreSQL errors, Kubernetes events, Nginx gateway errors, Redis CLUSTERDOWN, RabbitMQ consumer cancellations, etc.).
6.  **Chronological Order**: All logs in the `logs` array must be sorted by `timestamp` in ascending order.
7.  **Normal Phase**: Start with 10-15 INFO logs showing normal, healthy traffic before the incident begins.
8.  **Escalation**: After the normal phase, gradually increase severity — first WARNings, then ERRORs, FATALs, and ALERTs. The sequence should feel like watching an incident unfold in real-time.

### OUTPUT FORMAT (STRICT JSON):
Return ONLY a valid JSON object matching this structure exactly (do not wrap in markdown tags):
{
  "app_id": "The application ID (e.g., 'ecommerce-prod')",
  "incident_id": "The incident ID format INC-YYYY-XXXX",
  "scenario_title": "A short, human-readable title",
  "scenario_description": "Brief description of the storyline",
  "logs": [
    {
      "timestamp": "ISO 8601 string in UTC, e.g. 2026-03-26T10:01:05Z",
      "level": "INFO, WARN, ERROR, FATAL, or ALERT",
      "layer": "app, database, infrastructure, or monitoring",
      "service_id": "Node ID from the Graph",
      "message": "Realistic log text",
      "metadata": {} 
    }
  ]
}
"""

def build_user_prompt(graph_context: str) -> str:
    year = datetime.now(timezone.utc).year
    batch_id = str(uuid.uuid4())[:8].upper()
    incident_id = f"INC-{year}-{batch_id}"

    return f"""Here is the full Neo4j graph topology of the production system:

```cypher
{graph_context}
```

Now generate a single, self-contained incident log batch. 

Use incident_id = "{incident_id}"
The start time should be around 2026-03-26T09:00:00Z.

Choose a scenario that would genuinely challenge an AI incident analysis agent. 
Some ideas (but feel free to be creative):
- A shared infrastructure component (like `redis-cache` or `shared-analytics-db`) fails and creates a cross-app blast radius.
- A slow memory leak in one service that causes it to be OOMKilled, which then causes a cascade of 502s from the gateway.
- A RabbitMQ queue backlog growing because a consumer crashes, eventually causing the payment-api to block on publishing.
- A cross-service transaction where the root cause is subtle (e.g., a misconfigured connection pool that only manifests under load).

Remember: NO recovery logs. Stop at the incident peak.
"""


def generate_batch() -> GeneratedBatch:
    """Calls Gemini to generate a structured incident log batch."""
    print("📖 Loading graph topology...")
    graph_context = load_graph_topology()

    print("🤖 Calling Gemini to generate incident scenario...")
    model = genai.GenerativeModel(
        model_name="gemini-2.5-flash",
        system_instruction=SYSTEM_PROMPT,
        generation_config=genai.GenerationConfig(
            temperature=0.9,
            response_mime_type="application/json",
        ),
    )

    user_prompt = build_user_prompt(graph_context)
    response = model.generate_content(user_prompt)

    # Parse the structured response
    batch_data = json.loads(response.text)
    batch = GeneratedBatch(**batch_data)
    return batch


# ---------------------------------------------------------------------------
# Output Writer
# ---------------------------------------------------------------------------

def save_batch(batch: GeneratedBatch) -> Path:
    """Saves the generated batch to generated_logs/ as a JSON file."""
    output_path = OUTPUT_DIR / f"raw_batch_{batch.incident_id}.json"

    # Serialize, converting log entries to dicts
    output_data = {
        "app_id": batch.app_id,
        "incident_id": batch.incident_id,
        "scenario_title": batch.scenario_title,
        "scenario_description": batch.scenario_description,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "logs": [entry.model_dump() for entry in batch.logs]
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2)

    return output_path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("  ITSM Log Generator — LLM-Powered Incident Simulator")
    print("=" * 60)

    batch = generate_batch()

    print(f"\n✅ Scenario Generated: {batch.scenario_title}")
    print(f"   App:       {batch.app_id}")
    print(f"   Incident:  {batch.incident_id}")
    print(f"   Log Count: {len(batch.logs)} events")
    print(f"\n📋 Story: {batch.scenario_description}")

    output_path = save_batch(batch)
    print(f"\n💾 Saved to: {output_path}")
    print("=" * 60)


if __name__ == "__main__":
    main()
