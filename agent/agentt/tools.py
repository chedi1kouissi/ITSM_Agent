import json
import os
from langchain_core.tools import tool
from .database import get_db_connection

@tool
def create_incident_with_evidence(incident_id: str, evidence_items: list[dict], initial_summary: str = ""):
    """
    Creates a new incident and saves evidence in a single transaction.
    
    Args:
        incident_id: The ID for the new incident (e.g., "INC-2026-0001").
        evidence_items: List of dicts. Each dict MUST have:
                        - "log_line": The exact text of the log.
                        - "source": "app", "db", "infra", or "monitoring".
                        - "reasoning": Why this line is important (e.g. "Shows DB timeout").
                        - "timestamp": The timestamp from the log line.
        initial_summary: Optional brief description of the incident.
    """
    conn = get_db_connection()
    if not conn:
        return "Error: Could not connect to database."

    try:
        cur = conn.cursor()
        
        # 1. Create the incident first
        cur.execute("""
            INSERT INTO incidents (incident_id, status, agent_notes)
            VALUES (%s, %s, %s)
            ON CONFLICT (incident_id) DO NOTHING
        """, (
            incident_id,
            "ANALYZING",
            initial_summary or "Incident created - analyzing evidence"
        ))
        
        # 2. Save all evidence items
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
        return f"Successfully created incident {incident_id} and saved {saved_count} evidence items."
        
    except Exception as e:
        conn.rollback()
        return f"Error creating incident with evidence: {str(e)}"
    finally:
        cur.close()
        conn.close()

@tool
def calculate_risk_score(plan_text: str) -> int:
    """
    Calculates the risk (0-100) of a recovery plan based on dangerous keywords.
    """
    risk_score = 0
    plan_lower = plan_text.lower()
    
    # Risk Logic (Simple Heuristic)
    high_risk = ["kill", "drop", "truncate", "restart service", "global config", "delete"]
    medium_risk = ["scale", "clear cache", "index", "restart pod", "rollback"]
    
    for word in high_risk:
        if word in plan_lower:
            risk_score += 30
            
    for word in medium_risk:
        if word in plan_lower:
            risk_score += 10
            
    return min(risk_score, 100)

@tool
def finalize_itsm_ticket(incident_id: str, recovery_plan: str, risk_score: int, agent_notes: str):
    """
    Finalizes the incident by updating it with recovery plan and risk score.
    
    Args:
        incident_id: The ID for the ticket (must already exist from create_incident_with_evidence).
        recovery_plan: The full text of the proposed fix.
        risk_score: The score calculated by the risk tool.
        agent_notes: The "Internal Monologue" or summary of the agent's reasoning.
    """
    conn = get_db_connection()
    if not conn:
        return "Error: Could not connect to database."
        
    try:
        cur = conn.cursor()
        
        # 1. Update the incident with recovery plan
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
        
        # 2. Save recovery step
        cur.execute("""
            INSERT INTO recovery_steps (incident_id, step_order, step_description, risk_level, status)
            VALUES (%s, %s, %s, %s, %s)
        """, (
            incident_id,
            1,
            recovery_plan,
            "HIGH" if risk_score > 60 else ("MEDIUM" if risk_score > 30 else "LOW"),
            "PENDING"
        ))
        
        conn.commit()
        return f"Ticket {incident_id} finalized successfully with risk score {risk_score}."
        
    except Exception as e:
        conn.rollback()
        return f"Error finalizing ticket: {str(e)}"
    finally:
        cur.close()
        conn.close()