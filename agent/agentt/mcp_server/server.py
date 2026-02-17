from fastmcp import FastMCP
from typing import List, Dict, Any, Optional
import json
from datetime import datetime
import os
import sys

# Add parent directory to path to import agentt module
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from agentt.database import get_db_connection

# Initialize FastMCP Server
mcp = FastMCP("ITSM Agent Tools")

# ============================================================================
# WORKFLOW TOOL - Recommended for most cases
# ============================================================================

@mcp.tool()
def create_incident_workflow(
    incident_id: str,
    evidence_items: List[Dict[str, Any]],
    recovery_plan: str,
    recovery_steps: List[Dict[str, Any]],
    risk_score: int,
    agent_notes: str
) -> str:
    """
    Complete incident creation workflow - handles everything in a single transaction.
    
    This is the PRIMARY tool the agent should use for normal operation.
    
    Args:
        incident_id: Unique incident identifier (e.g., "INC-2026-0001")
        evidence_items: List of evidence dicts with keys:
            - log_line: The exact log text (TEXT)
            - source: "app", "db", "infra", or "monitoring" (VARCHAR 20)
            - timestamp: ISO timestamp string (will be converted to TIMESTAMP WITH TIME ZONE)
            - reasoning: Why this log is important (TEXT)
        recovery_plan: Text description of the recovery plan (goes in incidents.recovery_plan)
        recovery_steps: List of step dicts with keys:
            - step_order: Integer (1, 2, 3...)
            - step_description: What to do (TEXT)
            - risk_level: "HIGH", "MEDIUM", or "LOW" (VARCHAR 20)
        risk_score: Overall risk score (0-100) (INTEGER)
        agent_notes: Complete analysis and thought process (TEXT - goes in incidents.agent_notes)
    
    Returns:
        Success/error message
    """
    conn = get_db_connection()
    if not conn:
        return "Error: Could not connect to database."

    try:
        cur = conn.cursor()
        
        # 1. Create the incident (status defaults to 'OPEN', generated_at auto-set)
        cur.execute("""
            INSERT INTO incidents (incident_id, status, risk_score, recovery_plan, agent_notes)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (incident_id) DO NOTHING
        """, (
            incident_id,
            "OPEN",
            risk_score,
            recovery_plan,
            agent_notes
        ))
        
        # 2. Save all evidence (created_at auto-set)
        evidence_count = 0
        for item in evidence_items:
            # Convert timestamp string to proper format if needed
            timestamp_val = item.get("timestamp")
            
            cur.execute("""
                INSERT INTO evidence (incident_id, log_line, source, timestamp, reasoning)
                VALUES (%s, %s, %s, %s, %s)
            """, (
                incident_id,
                item.get("log_line"),
                item.get("source"),
                timestamp_val,
                item.get("reasoning")
            ))
            evidence_count += 1
        
        # 3. Save all recovery steps (status defaults to 'PENDING', created_at auto-set)
        steps_count = 0
        for step in recovery_steps:
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
            steps_count += 1
        
        # 4. Log this workflow execution as an agent action (created_at auto-set)
        cur.execute("""
            INSERT INTO agent_actions (
                incident_id, 
                action_type, 
                input_params, 
                output_result, 
                agent_reasoning
            )
            VALUES (%s, %s, %s, %s, %s)
        """, (
            incident_id,
            "create_incident_workflow",
            json.dumps({
                "evidence_count": evidence_count,
                "steps_count": steps_count,
                "risk_score": risk_score
            }),
            json.dumps({"status": "success"}),
            agent_notes
        ))
        
        conn.commit()
        return f"✅ Incident {incident_id} created successfully with {evidence_count} evidence items and {steps_count} recovery steps."
        
    except Exception as e:
        conn.rollback()
        return f"❌ Error in workflow: {str(e)}"
    finally:
        cur.close()
        conn.close()


# ============================================================================
# GRANULAR TOOLS - For advanced/incremental workflows
# ============================================================================

@mcp.tool()
def initialize_incident(incident_id: str, initial_summary: str = "") -> str:
    """
    Creates a new incident record with ANALYZING status.
    Use this when you want to save evidence incrementally.
    
    Schema mapping:
    - incident_id: VARCHAR(50) UNIQUE NOT NULL
    - status: VARCHAR(20) - defaults to 'ANALYZING' (normally 'OPEN')
    - agent_notes: TEXT - initial summary goes here
    - generated_at: TIMESTAMP WITH TIME ZONE - auto-set
    
    Args:
        incident_id: Unique incident identifier
        initial_summary: Optional brief description (goes in agent_notes)
    """
    conn = get_db_connection()
    if not conn:
        return "Error: Could not connect to database."

    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO incidents (incident_id, status, agent_notes)
            VALUES (%s, %s, %s)
            ON CONFLICT (incident_id) DO NOTHING
        """, (
            incident_id,
            "ANALYZING",
            initial_summary or "Incident initialized"
        ))
        
        # Log action
        cur.execute("""
            INSERT INTO agent_actions (incident_id, action_type, input_params, output_result)
            VALUES (%s, %s, %s, %s)
        """, (
            incident_id,
            "initialize_incident",
            json.dumps({"summary": initial_summary}),
            json.dumps({"status": "success"})
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
        
        # Log action
        cur.execute("""
            INSERT INTO agent_actions (incident_id, action_type, input_params, output_result)
            VALUES (%s, %s, %s, %s)
        """, (
            incident_id,
            "add_evidence",
            json.dumps({"count": saved_count}),
            json.dumps({"status": "success", "items_saved": saved_count})
        ))
        
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
        
        # Log action
        cur.execute("""
            INSERT INTO agent_actions (incident_id, action_type, input_params, output_result)
            VALUES (%s, %s, %s, %s)
        """, (
            incident_id,
            "add_recovery_steps",
            json.dumps({"count": saved_count}),
            json.dumps({"status": "success", "steps_saved": saved_count})
        ))
        
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
    agent_notes: str
) -> str:
    """
    Finalizes an incident by updating it with recovery plan and risk score.
    Changes status from ANALYZING to OPEN.
    
    Schema mapping (incidents table):
    - status: VARCHAR(20) - changed to 'OPEN'
    - risk_score: INTEGER
    - recovery_plan: TEXT
    - agent_notes: TEXT - complete analysis
    
    Args:
        incident_id: Existing incident ID
        recovery_plan: TEXT - summary of what caused the incident (goes in recovery_plan column)
        risk_score: INTEGER (0-100)
        agent_notes: TEXT - complete analysis and reasoning
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
        
        # Log action
        cur.execute("""
            INSERT INTO agent_actions (incident_id, action_type, input_params, output_result, agent_reasoning)
            VALUES (%s, %s, %s, %s, %s)
        """, (
            incident_id,
            "finalize_incident",
            json.dumps({"risk_score": risk_score}),
            json.dumps({"status": "success"}),
            agent_notes
        ))
        
        conn.commit()
        return f"✅ Incident {incident_id} finalized with risk score {risk_score}."
        
    except Exception as e:
        conn.rollback()
        return f"❌ Error: {str(e)}"
    finally:
        cur.close()
        conn.close()


@mcp.tool()
def calculate_risk_score(plan_text: str) -> int:
    """
    Calculates the risk (0-100) of a recovery plan based on dangerous keywords.
    This is a utility tool that doesn't touch the database.
    
    Args:
        plan_text: The recovery plan text to analyze
        
    Returns:
        Risk score (0-100)
    """
    risk_score = 0
    plan_lower = plan_text.lower()
    
    # High risk operations
    high_risk = ["kill", "drop", "truncate", "delete database", "global config", "delete all", "rm -rf"]
    medium_risk = ["restart service", "scale down", "clear cache", "rebuild index", "restart pod", "rollback"]
    low_risk = ["log", "monitor", "check status", "view", "read"]
    
    for word in high_risk:
        if word in plan_lower:
            risk_score += 30
            
    for word in medium_risk:
        if word in plan_lower:
            risk_score += 15
    
    for word in low_risk:
        if word in plan_lower:
            risk_score += 5
            
    return min(risk_score, 100)


@mcp.tool()
def log_agent_action(
    incident_id: str,
    action_type: str,
    input_params: Dict[str, Any],
    output_result: Dict[str, Any],
    reasoning: str = "",
    observation: str = ""
) -> str:
    """
    Manually logs an agent action for audit purposes.
    Most tools auto-log, but use this for custom actions.
    
    Args:
        incident_id: Related incident ID (optional)
        action_type: Type of action (e.g., "web_search", "analysis")
        input_params: What the agent provided as input
        output_result: What was returned
        reasoning: Why the agent took this action
        observation: What the agent learned from the result
    """
    conn = get_db_connection()
    if not conn:
        return "Error: Could not connect to database."

    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO agent_actions (
                incident_id,
                action_type,
                input_params,
                output_result,
                agent_reasoning,
                observation
            )
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            incident_id or None,
            action_type,
            json.dumps(input_params),
            json.dumps(output_result),
            reasoning,
            observation
        ))
        
        conn.commit()
        return f"✅ Action logged: {action_type}"
        
    except Exception as e:
        conn.rollback()
        return f"❌ Error: {str(e)}"
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    mcp.run()