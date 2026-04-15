#mcp_server/server.py
from fastmcp import FastMCP
from typing import List, Dict, Any, Optional
import json
from datetime import datetime
import os
import sys
from neo4j import GraphDatabase
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()
_genai_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# Add parent directory to path to import agentt module
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from agentt.database import get_db_connection


neo4j_driver = GraphDatabase.driver(
    os.getenv("NEO4J_URI", "neo4j://127.0.0.1:7687"),
    auth=(os.getenv("NEO4J_USER", "neo4j"), os.getenv("NEO4J_PASSWORD", "password"))
)

# Initialize FastMCP Server
mcp = FastMCP("ITSM Agent Tools")


# ============================================================================
# GRAPH TOPOLOGY TOOLS
# ============================================================================

@mcp.tool()
def get_service_dependencies(app_id: str) -> str:
    """
    Fetches the full 2-hop service dependency map for an application from Neo4j.
    Returns node types (Service / Database / Infrastructure), relationship types,
    and edge properties (pool_size, latency_slo_ms, use_case, etc.).
    Call this IMMEDIATELY after initialize_incident to understand the architecture.

    Args:
        app_id: The application ID to look up (must match Application.id in Neo4j).
    """
    # Hop 1: direct dependencies of services in this app
    query_hop1 = """
    MATCH (a:Application {id: $app_id})-[:CONTAINS]->(s)
    MATCH (s)-[r]->(dep)
    WHERE NOT type(r) = 'CONTAINS'
    RETURN
        labels(s)[0]   AS src_type,
        s.id           AS src_id,
        s.criticality  AS src_criticality,
        type(r)        AS rel_type,
        properties(r)  AS rel_props,
        labels(dep)[0] AS dep_type,
        dep.id         AS dep_id,
        dep.criticality AS dep_criticality
    ORDER BY src_id
    """
    # Hop 2: what do those dependencies depend on?
    query_hop2 = """
    MATCH (a:Application {id: $app_id})-[:CONTAINS]->(s)
    MATCH (s)-[]->(dep)-[r2]->(dep2)
    WHERE NOT type(r2) = 'CONTAINS'
    RETURN
        labels(dep)[0]  AS src_type,
        dep.id          AS src_id,
        type(r2)        AS rel_type,
        properties(r2)  AS rel_props,
        labels(dep2)[0] AS dep_type,
        dep2.id         AS dep_id
    ORDER BY dep.id
    """
    try:
        lines = [f"=== SERVICE DEPENDENCY MAP: {app_id} ===\n"]
        with neo4j_driver.session() as session:
            # --- Hop 1 ---
            result1 = session.run(query_hop1, app_id=app_id)
            records1 = list(result1)
            if not records1:
                return f"No topology found for app_id='{app_id}'. Check that this ID exists in Neo4j."

            lines.append("-- Direct Dependencies (Hop 1) --")
            for r in records1:
                props = dict(r["rel_props"] or {})
                prop_str = ", ".join(f"{k}={v}" for k, v in props.items()) if props else ""
                crit = f" [{r['src_criticality']}]" if r.get("src_criticality") else ""
                dep_crit = f" [{r['dep_criticality']}]" if r.get("dep_criticality") else ""
                lines.append(
                    f"  {r['src_type']}:{r['src_id']}{crit}"
                    f" --[{r['rel_type']}{': ' + prop_str if prop_str else ''}]-->"
                    f" {r['dep_type']}:{r['dep_id']}{dep_crit}"
                )

            # --- Hop 2 ---
            result2 = session.run(query_hop2, app_id=app_id)
            records2 = list(result2)
            if records2:
                lines.append("\n-- Transitive Dependencies (Hop 2) --")
                for r in records2:
                    props = dict(r["rel_props"] or {})
                    prop_str = ", ".join(f"{k}={v}" for k, v in props.items()) if props else ""
                    lines.append(
                        f"  {r['src_type']}:{r['src_id']}"
                        f" --[{r['rel_type']}{': ' + prop_str if prop_str else ''}]-->"
                        f" {r['dep_type']}:{r['dep_id']}"
                    )

        return "\n".join(lines)
    except Exception as e:
        return f"Error fetching service dependencies: {str(e)}"


@mcp.tool()
def get_blast_radius(resource_id: str) -> str:
    """
    Given a failing resource (Service, Database, or Infrastructure node ID),
    finds ALL other services — across ALL apps — that depend on the same resource.
    Use this to assess cross-app impact when a shared resource is suspected as root cause.
    Each affected service appears only ONCE (multiple relationship types are collapsed).

    Args:
        resource_id: The ID of the failing node (e.g. 'payment-db', 'redis-cache').
    """
    query = """
    MATCH (victim)-[r]->(shared {id: $resource_id})
    OPTIONAL MATCH (app)-[:CONTAINS]->(victim)
    WITH
        victim,
        app,
        labels(victim)[0]  AS victim_type,
        labels(shared)[0]  AS shared_type,
        shared.id          AS shared_id,
        collect(DISTINCT type(r)) AS rel_types
    RETURN
        victim_type,
        victim.id           AS victim_id,
        victim.criticality  AS victim_criticality,
        victim.owner_team   AS victim_team,
        rel_types,
        shared_type,
        shared_id,
        app.id              AS app_id,
        app.tier            AS app_tier
    ORDER BY victim.criticality
    """
    try:
        with neo4j_driver.session() as session:
            result = session.run(query, resource_id=resource_id)
            records = list(result)
            if not records:
                return f"No dependents found for resource_id='{resource_id}'."

            lines = [f"=== BLAST RADIUS: {resource_id} ===\n"]
            shared_label = records[0]["shared_type"]
            lines.append(f"Failing resource: {shared_label}:{resource_id}")
            lines.append(f"Affected services ({len(records)} unique):\n")
            for r in records:
                crit = r.get("victim_criticality") or "?"
                team = r.get("victim_team") or "unknown"
                app = r.get("app_id") or "standalone"
                tier = r.get("app_tier") or ""
                rel_types = ", ".join(r["rel_types"])
                lines.append(
                    f"  [{crit}] {r['victim_type']}:{r['victim_id']}"
                    f"  (app={app}{' ' + tier if tier else ''}, team={team})"
                    f"  via [{rel_types}]"
                )
        return "\n".join(lines)
    except Exception as e:
        return f"Error fetching blast radius: {str(e)}"


@mcp.tool()
def get_infrastructure_routes(app_id: str) -> str:
    """
    Returns the infrastructure layer (API gateways, load balancers) that routes
    traffic into services of the given application.
    Use this when logs show gateway timeouts or 502/504 errors — the infra node
    properties (timeout_ms, protocol) help pinpoint misconfiguration.

    Args:
        app_id: The application ID to look up.
    """
    query = """
    MATCH (a:Application {id: $app_id})-[:CONTAINS]->(s)
    MATCH (infra:Infrastructure)-[r:ROUTES_TO]->(s)
    RETURN
        infra.id          AS infra_id,
        infra.name        AS infra_name,
        infra.type        AS infra_type,
        infra.host        AS infra_host,
        infra.timeout_ms  AS infra_timeout_ms,
        infra.criticality AS infra_criticality,
        properties(r)     AS route_props,
        s.id              AS service_id,
        s.criticality     AS service_criticality
    ORDER BY infra.id
    """
    try:
        with neo4j_driver.session() as session:
            result = session.run(query, app_id=app_id)
            records = list(result)
            if not records:
                return f"No infrastructure routing found for app_id='{app_id}'."

            lines = [f"=== INFRASTRUCTURE ROUTES: {app_id} ===\n"]
            for r in records:
                props = dict(r["route_props"] or {})
                prop_str = ", ".join(f"{k}={v}" for k, v in props.items()) if props else ""
                lines.append(
                    f"  Infrastructure:{r['infra_id']} ({r['infra_type']}, host={r['infra_host']}, "
                    f"timeout={r['infra_timeout_ms']}ms, [{r['infra_criticality']}])"
                    f"\n    --[ROUTES_TO{': ' + prop_str if prop_str else ''}]--> "
                    f"Service:{r['service_id']} [{r['service_criticality']}]"
                )
        return "\n".join(lines)
    except Exception as e:
        return f"Error fetching infrastructure routes: {str(e)}"

    
    

@mcp.tool()
def initialize_incident(incident_id: str, app_id: str = "", initial_summary: str = "") -> str:
    """
    Creates a new incident record with ANALYZING status.
    Use this when you want to save evidence incrementally.
    
    Schema mapping:
    - incident_id: VARCHAR(50) UNIQUE NOT NULL
    - app_id: VARCHAR(50) - optional app identifier
    - status: VARCHAR(20) - defaults to 'ANALYZING' (normally 'OPEN')
    - agent_notes: TEXT - initial summary goes here
    - generated_at: TIMESTAMP WITH TIME ZONE - auto-set
    
    Args:
        incident_id: Unique incident identifier
        app_id: Optional app identifier associated with this incident
        initial_summary: Optional brief description (goes in agent_notes)
    """
    conn = get_db_connection()
    if not conn:
        return "Error: Could not connect to database."

    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO incidents (incident_id, app_id, status, agent_notes)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (incident_id) DO NOTHING
        """, (
            incident_id,
            app_id or None,
            "ANALYZING",
            initial_summary or "Incident initialized"
        ))
        
      
        conn.commit()
        return f"✅ Incident {incident_id} initialized."
        
    except Exception as e:
        conn.rollback()
        return f"❌ Error: {str(e)}"
    finally:
        cur.close()
        conn.close()


@mcp.tool()
def add_evidence(incident_id: str, evidence_items: List[Dict[str, Any]]) -> str:
    """
    Adds evidence to an existing incident.
    Can be called multiple times to add evidence incrementally.
    
    Schema mapping (evidence table):
    - incident_id: VARCHAR(50) - REFERENCES incidents(incident_id)
    - log_line: TEXT NOT NULL
    - source: VARCHAR(20) - "app", "db", "infra", or "monitoring"
    - timestamp: TIMESTAMP WITH TIME ZONE
    - reasoning: TEXT
    - created_at: TIMESTAMP WITH TIME ZONE - auto-set
    
    Args:
        incident_id: Existing incident ID
        evidence_items: List of dicts with keys:
            - log_line (required): TEXT
            - source: VARCHAR(20)
            - timestamp: ISO string (converted to TIMESTAMP WITH TIME ZONE)
            - reasoning: TEXT
    """
    conn = get_db_connection()
    if not conn:
        return "Error: Could not connect to database."

    try:
        cur = conn.cursor()
        saved_count = 0
        
        for item in evidence_items:
            cur.execute("""
                INSERT INTO evidence (incident_id, log_line, source, timestamp, reasoning)
                VALUES (%s, %s, %s, %s, %s)
            """, (
                incident_id,
                item.get("log_line"),
                item.get("source"),
                item.get("timestamp"),
                item.get("reasoning")
            ))
            saved_count += 1
        
       
        
        conn.commit()
        return f"✅ Added {saved_count} evidence items to {incident_id}."
        
    except Exception as e:
        conn.rollback()
        return f"❌ Error: {str(e)}"
    finally:
        cur.close()
        conn.close()


@mcp.tool()
def add_recovery_steps(incident_id: str, steps: List[Dict[str, Any]]) -> str:
    """
    Adds recovery steps to an existing incident.
    
    Schema mapping (recovery_steps table):
    - incident_id: VARCHAR(50) - REFERENCES incidents(incident_id)
    - step_order: INTEGER NOT NULL
    - step_description: TEXT NOT NULL
    - risk_level: VARCHAR(20)
    - status: VARCHAR(20) - defaults to 'PENDING'
    - created_at: TIMESTAMP WITH TIME ZONE - auto-set
    
    Args:
        incident_id: Existing incident ID
        steps: List of dicts with keys:
            - step_order (required): INTEGER
            - step_description (required): TEXT
            - risk_level: VARCHAR(20) - "HIGH", "MEDIUM", or "LOW"
    """
    conn = get_db_connection()
    if not conn:
        return "Error: Could not connect to database."

    try:
        cur = conn.cursor()
        saved_count = 0
        
        for step in steps:
            cur.execute("""
                INSERT INTO recovery_steps (incident_id, step_order, step_description, risk_level, status)
                VALUES (%s, %s, %s, %s, %s)
            """, (
                incident_id,
                step.get("step_order"),
                step.get("step_description"),
                step.get("risk_level", "MEDIUM"),
                "PENDING"
            ))
            saved_count += 1
        
        conn.commit()
        return f"✅ Added {saved_count} recovery steps to {incident_id}."
        
    except Exception as e:
        conn.rollback()
        return f"❌ Error: {str(e)}"
    finally:
        cur.close()
        conn.close()


@mcp.tool()
def finalize_incident(
    incident_id: str,
    recovery_plan: str,
    risk_score: int,
    agent_notes: str,
    app_id: str = ""
) -> str:
    """
    Finalizes an incident by updating it with recovery plan and risk score.
    Changes status from ANALYZING to OPEN.
    
    Schema mapping (incidents table):
    - status: VARCHAR(20) - changed to 'OPEN'
    - risk_score: INTEGER
    - recovery_plan: TEXT
    - agent_notes: TEXT - complete analysis
    - app_id: VARCHAR(50) 
    
    Args:
        incident_id: Existing incident ID
        recovery_plan: TEXT - summary of what caused the incident (goes in recovery_plan column)
        risk_score: INTEGER (0-100)
        agent_notes: TEXT - complete analysis and reasoning
        app_id: Optional app identifier (used when logging the finalize action)
    """
    conn = get_db_connection()
    if not conn:
        return "Error: Could not connect to database."

    try:
        cur = conn.cursor()
        
        cur.execute("""
            UPDATE incidents 
            SET status = %s,
                risk_score = %s,
                recovery_plan = %s,
                agent_notes = %s
            WHERE incident_id = %s
        """, (
            "OPEN",
            risk_score,
            recovery_plan,
            agent_notes,
            incident_id
        ))
        
        
        
        conn.commit()
        return f"✅ Incident {incident_id} finalized with risk score {risk_score}."
        
    except Exception as e:
        conn.rollback()
        return f"❌ Error: {str(e)}"
    finally:
        cur.close()
        conn.close()


# ============================================================================
# LINEAR INTEGRATION TOOL
# ============================================================================

@mcp.tool()
def create_linear_ticket(
    incident_id: str,
    title: str,
    description: str,
    risk_score: int,
) -> str:
    """
    Creates a Linear issue for the current incident, then stores the returned
    linear_issue_id and linear_identifier in the PostgreSQL incidents table.
    Call this immediately after finalize_incident.

    The returned linear_issue_id MUST be passed to save_resolved_ticket so the
    ResolvedTicket node in Neo4j can be looked up by the webhook listener.

    Args:
        incident_id: The ITSM incident ID (e.g. 'INC-2026-A1B2C3D4')
        title:       Short Linear issue title
                     (e.g. 'INC-2026-A1B2C3D4: payment-api upstream timeout')
        description: Markdown body — recovery plan + root cause + evidence summary.
                     Use **bold** headers to make it readable in Linear.
        risk_score:  Integer 0–100; maps to Linear priority
                     (>=61 → Urgent, 31–60 → High, 0–30 → Medium)
    """
    try:
        from agentt.linear_client import create_issue
        result = create_issue(
            title=title,
            description=description,
            risk_score=risk_score,
        )
        linear_issue_id = result["id"]
        linear_identifier = result["identifier"]
        linear_url = result["url"]

        # Persist the Linear IDs in PostgreSQL incidents table
        conn = get_db_connection()
        if not conn:
            return (
                f"✅ Linear issue created: {linear_identifier} | ID: {linear_issue_id} | "
                f"URL: {linear_url}\n"
                f"⚠️ Could not update PostgreSQL (connection failed). "
                f"Pass linear_issue_id='{linear_issue_id}' to save_resolved_ticket."
            )
        try:
            cur = conn.cursor()
            cur.execute("""
                UPDATE incidents
                SET linear_issue_id   = %s,
                    linear_identifier = %s
                WHERE incident_id = %s
            """, (linear_issue_id, linear_identifier, incident_id))
            conn.commit()
        except Exception as db_err:
            conn.rollback()
            return (
                f"✅ Linear issue created: {linear_identifier} | ID: {linear_issue_id} | "
                f"URL: {linear_url}\n"
                f"⚠️ PostgreSQL update failed: {db_err}. "
                f"Pass linear_issue_id='{linear_issue_id}' to save_resolved_ticket."
            )
        finally:
            cur.close()
            conn.close()

        return (
            f"✅ Linear issue created and linked.\n"
            f"   Identifier : {linear_identifier}\n"
            f"   ID (UUID)  : {linear_issue_id}\n"
            f"   URL        : {linear_url}\n"
            f"   Next step  : call save_resolved_ticket with "
            f"linear_issue_id='{linear_issue_id}'"
        )

    except Exception as e:
        return f"❌ Error creating Linear ticket: {str(e)}"


@mcp.tool()
def calculate_risk_score(plan_text: str) -> int:
    """
    Calculates the risk (0-100) of a recovery plan based on dangerous keywords.
    This is a utility tool that doesn't touch the database.

    Risk tiers:
    - HIGH (+30): Destructive or irreversible operations (drop, delete, kill, wipe, rm -rf)
    - MEDIUM (+15): Disruptive but recoverable (restart, clear cache, rollback, config changes, scaling)
    - LOW (+5): Observational only (monitor, log, check, view, read)

    Args:
        plan_text: The recovery plan text to analyze

    Returns:
        Risk score (0-100)
    """
    risk_score = 0
    plan_lower = plan_text.lower()

    high_risk = [
        "kill", "drop", "truncate", "delete database", "delete all",
        "rm -rf", "wipe", "force delete", "purge", "destroy",
        "overwrite production", "bypass"
    ]
    medium_risk = [
        # Restarts (any form)
        "restart", "rolling restart", "restart service", "restart pod",
        "reboot", "bounce",
        # Scaling
        "scale", "scale down", "scale up", "increase replica", "decrease replica",
        # Config changes
        "modify parameter", "change config", "update config", "global config",
        "increase max_conn", "max_connections", "modify setting",
        # Cache/index operations
        "clear cache", "flush cache", "rebuild index", "reindex",
        # Rollback
        "rollback", "revert", "downgrade",
        # Migration
        "migrate", "failover"
    ]
    low_risk = [
        "log", "monitor", "check status", "check", "view", "read",
        "analyze", "investigate", "inspect", "observe"
    ]

    matched_high = []
    matched_medium = []
    matched_low = []

    for word in high_risk:
        if word in plan_lower:
            risk_score += 30
            matched_high.append(word)

    for word in medium_risk:
        if word in plan_lower:
            risk_score += 15
            matched_medium.append(word)

    for word in low_risk:
        if word in plan_lower:
            risk_score += 5
            matched_low.append(word)

    return min(risk_score, 100)



# ============================================================================
# LTM TOOLS
# ============================================================================

def _embed(text: str) -> List[float]:
    result = _genai_client.models.embed_content(
        model="gemini-embedding-001",
        contents=text,
        config=types.EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT")
    )
    return result.embeddings[0].values

def _embed_query(text: str) -> List[float]:
    result = _genai_client.models.embed_content(
        model="gemini-embedding-001",
        contents=text,
        config=types.EmbedContentConfig(task_type="RETRIEVAL_QUERY")
    )
    return result.embeddings[0].values
 
# ============================================================================
# TOOL 1: save_resolved_ticket
# Call this right after finalize_incident
# ============================================================================
 
@mcp.tool()
def save_resolved_ticket(
    incident_id: str,
    app_id: str,
    root_cause_node_id: str,
    affected_service_ids: List[str],
    problem_text: str,
    solution_text: str,
    risk_score: int,
    linear_issue_id: str = "",
    human_notes: str = ""
) -> str:
    """
    Creates a ResolvedTicket node in Neo4j, embeds problem and solution text
    as vectors, and links the ticket to the root cause node and all affected
    service nodes via HAS_MEMORY relationships.
 
    Call this IMMEDIATELY after finalize_incident.
 
    Args:
        incident_id: The incident ID (e.g. 'INC-2026-0004')
        app_id: The application ID (e.g. 'admin-portal')
        root_cause_node_id: The Neo4j node ID of the root cause
                            (e.g. 'prod-node-2', 'payment-db', 'redis-cache')
        affected_service_ids: List of service node IDs directly affected
                              (e.g. ['reporting-api', 'admin-service'])
        problem_text: Root cause summary + key evidence. This is what gets
                      embedded for future similarity search.
        solution_text: Full recovery plan + agent notes. Combined with
                       human_notes before embedding.
        risk_score: Risk score from calculate_risk_score (0-100)
        human_notes: Optional human-added notes (leave empty initially).
                     When updated later, the solution embedding is recomputed.
    """
    try:
        # Build the full solution text (human notes baked in)
        full_solution = solution_text
        if human_notes:
            full_solution = f"{solution_text}\n\nHuman notes: {human_notes}"

        # Embed both vectors (done BEFORE opening the transaction to avoid
        # holding a DB connection open during slow API calls)
        problem_embedding = _embed(problem_text)
        solution_embedding = _embed(full_solution)

        # All node IDs to link (root cause + affected services, deduplicated)
        all_linked_nodes = list(set([root_cause_node_id] + affected_service_ids))

        # Use a single explicit transaction so the node + all HAS_MEMORY edges
        # are written atomically — either everything commits or nothing does.
        with neo4j_driver.session() as session:
            with session.begin_transaction() as tx:
                # 1. Create / update the ResolvedTicket node
                tx.run("""
                    MERGE (t:ResolvedTicket {incident_id: $incident_id})
                    SET t.app_id             = $app_id,
                        t.problem_text       = $problem_text,
                        t.solution_text      = $solution_text,
                        t.human_notes        = $human_notes,
                        t.risk_score         = $risk_score,
                        t.linear_issue_id    = $linear_issue_id,
                        t.problem_embedding  = $problem_embedding,
                        t.solution_embedding = $solution_embedding,
                        t.created_at         = datetime()
                """, {
                    "incident_id":        incident_id,
                    "app_id":             app_id,
                    "problem_text":       problem_text,
                    "solution_text":      solution_text,
                    "human_notes":        human_notes,
                    "risk_score":         risk_score,
                    "linear_issue_id":    linear_issue_id,
                    "problem_embedding":  problem_embedding,
                    "solution_embedding": solution_embedding,
                })

                # 2. Link to every relevant node (root cause + affected services)
                missing_nodes = []
                for node_id in all_linked_nodes:
                    result = tx.run("""
                        MATCH (n {id: $node_id})
                        MATCH (t:ResolvedTicket {incident_id: $incident_id})
                        MERGE (n)-[:HAS_MEMORY]->(t)
                        RETURN count(n) AS linked
                    """, {
                        "node_id":     node_id,
                        "incident_id": incident_id,
                    })
                    record = result.single()
                    if not record or record["linked"] == 0:
                        missing_nodes.append(node_id)

                tx.commit()

        linked_str = ", ".join(all_linked_nodes)
        warning = ""
        if missing_nodes:
            warning = f" ⚠️ Warning: could not link to nodes (not found in graph): {', '.join(missing_nodes)}."
        return (
            f"✅ ResolvedTicket '{incident_id}' saved and linked to: {linked_str}. "
            f"Problem and solution embeddings stored (768-dim).{warning}"
        )

    except Exception as e:
        return f"❌ Error saving resolved ticket: {str(e)}"
 
 
# ============================================================================
# TOOL 2: search_memory
# Call this after get_service_dependencies at the start of a new incident
# ============================================================================
 
@mcp.tool()
def search_memory(
    node_id: str,
    current_problem: str,
    top_k: int = 3
) -> str:
    """
    Searches for similar past incidents linked to a specific graph node
    (service, database, or infrastructure) using vector similarity on the
    problem embedding. Returns the most relevant historical fixes.
 
    Call this after get_service_dependencies when you suspect a node is
    involved in the current incident. The search is LOCALIZED — it only
    searches tickets linked to that specific node, not the entire database.
 
    Args:
        node_id: The Neo4j node ID to search memory for
                 (e.g. 'reporting-api', 'payment-db', 'redis-cache')
        current_problem: Description of the current incident's symptoms
                         and suspected root cause. This is embedded and
                         compared against historical problem vectors.
        top_k: Number of similar past tickets to return (default: 3)
    """
    try:
        query_embedding = _embed_query(current_problem)
 
        with neo4j_driver.session() as session:
            # Localized vector search: only within tickets linked to this node
            result = session.run("""
                MATCH (n {id: $node_id})-[:HAS_MEMORY]->(t:ResolvedTicket)
                WITH t,
                     vector.similarity.cosine(t.problem_embedding, $query_embedding) AS score
                ORDER BY score DESC
                LIMIT $top_k
                RETURN t.incident_id    AS incident_id,
                       t.app_id         AS app_id,
                       t.problem_text   AS problem_text,
                       t.solution_text  AS solution_text,
                       t.human_notes    AS human_notes,
                       t.risk_score     AS risk_score,
                       t.created_at     AS created_at,
                       score
            """, {
                "node_id":         node_id,
                "query_embedding": query_embedding,
                "top_k":           top_k,
            })
 
            records = list(result)
 
        if not records:
            return (
                f"No historical incidents found for node '{node_id}'. "
                f"This may be the first incident involving this component."
            )
 
        lines = [f"=== MEMORY SEARCH: {node_id} (top {len(records)} matches) ===\n"]
 
        for i, r in enumerate(records, 1):
            score_pct = round(r["score"] * 100, 1)
            lines.append(f"--- Match #{i} | {r['incident_id']} | similarity: {score_pct}% ---")
            lines.append(f"App: {r['app_id']} | Risk Score: {r['risk_score']} | Date: {r['created_at']}")
            lines.append(f"\nPAST PROBLEM:\n{r['problem_text']}")
            lines.append(f"\nPAST SOLUTION:\n{r['solution_text']}")
 
            if r["human_notes"]:
                lines.append(f"\n⚠️  HUMAN NOTES (apply these first):\n{r['human_notes']}")
 
            lines.append("")  # spacing between matches
 
        return "\n".join(lines)
 
    except Exception as e:
        return f"❌ Error searching memory: {str(e)}"