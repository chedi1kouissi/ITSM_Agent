#state.py
import operator
from typing import Annotated, List, TypedDict, Optional
from pydantic import BaseModel, Field

# --- structured Objects ---

class Evidence(BaseModel):
    """Represents a specific log line saved as proof of the root cause."""
    log_line: str = Field(description="The exact raw text of the log line")
    source: str = Field(description="Origin of the log: 'app', 'db', 'infra', or 'monitor'")
    timestamp: str = Field(description="Time of the event (ISO format)")
    reasoning: str = Field(description="Why this specific log is relevant to the incident")

class RecoveryPlan(BaseModel):
    """The structured output for the fix."""
    steps: List[str] = Field(description="Ordered list of remediation steps")
    estimated_risk: int = Field(description="Initial risk estimation (0-100)")
    rollback_plan: str = Field(description="What to do if the fix fails")

# --- The Graph State ---

class AgentState(TypedDict):
    """
    The memory of the agent during the execution loop.
    messages: Holds the conversation history (User inputs + AI responses).
    """
    # Raw Inputs
    raw_logs: str  # The massive log dump
    
    # Structured Memory (The "Clean" Context)
    evidence_chain: Annotated[List[Evidence], operator.add] # Appends new evidence
    
    # neo4j graph context (optional, can be None if not used)
    topology_context: Optional[str]
    
    # Outputs
    root_cause: Optional[str]
    recovery_plan: Optional[RecoveryPlan]
    final_risk_score: Optional[int]
    ticket_status: str # "analyzing", "ticket_created", "human_approval_needed"

    # Linear integration (populated after create_linear_ticket succeeds)
    linear_issue_id: Optional[str]

    # Standard LangGraph message history
    messages: Annotated[List[str], operator.add]