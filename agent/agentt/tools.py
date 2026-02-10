import json
import os
from langchain_core.tools import tool

from .state import AgentState

# Path where the final tickets are saved
DB_FILE = "data/incidents_db.json"

@tool
def save_relevant_evidence(evidence_items: list[dict]):
    """
    Saves specific log lines that serve as evidence for the root cause.
    
    Args:
        evidence_items: List of dicts. Each dict MUST have:
                        - "log_line": The exact text of the log.
                        - "source": "app", "db", "infra", or "monitoring".
                        - "reasoning": Why this line is important (e.g. "Shows DB timeout").
    """
    # In a real app, this would push to the state. 
    # Here, we return a success message so the LLM knows it "worked".
    return f"Successfully saved {len(evidence_items)} evidence items."

@tool
def calculate_risk_score(plan_text: str) -> int:
    """
    Calculates the risk (0-100) of a recovery plan based on dangerous keywords.
    """
    risk_score = 0
    plan_lower = plan_text.lower()
    
    # Risk Logic
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
def create_itsm_ticket(incident_id: str, recovery_plan: str, risk_score: int, evidence_list: list[dict], internal_monologue: str):
    """
    Finalizes the process by saving the ticket to the database.
    
    Args:
        incident_id: The ID for the ticket.
        recovery_plan: The full text of the proposed fix.
        risk_score: The score calculated by the risk tool.
        evidence_list: The list of evidence items found during analysis.
        internal_monologue: A brief summary of the agent's reasoning.
    """
    ticket_data = {
        "incident_id": incident_id,
        "status": "OPEN",
        "risk_score": risk_score,
        "recovery_plan": recovery_plan,
        "evidence": evidence_list,  # Use the data passed by the LLM
        "agent_notes": internal_monologue,
        "requires_human_approval": risk_score > 30,
        "created_at": "2026-02-05T10:08:00Z" # You can use datetime.now() here
    }
    
    os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)
    
    if os.path.exists(DB_FILE):
        with open(DB_FILE, 'r') as f:
            try:
                db_data = json.load(f)
            except json.JSONDecodeError:
                db_data = []
    else:
        db_data = []
        
    db_data.append(ticket_data)
    
    with open(DB_FILE, 'w') as f:
        json.dump(db_data, f, indent=2)
        
    return f"Ticket {incident_id} saved successfully."