import os
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import StateGraph
from langgraph.prebuilt import ToolNode, tools_condition
from langchain_core.messages import SystemMessage
from langchain_core.tools import StructuredTool
from typing import List, Dict, Any

from agentt.state import AgentState
from agentt.mcp_server.server import (
    initialize_incident,
    add_evidence,
    add_recovery_steps,
    calculate_risk_score,
    finalize_incident,
    get_service_dependencies,
    get_blast_radius,
    get_infrastructure_routes,
)

load_dotenv()

# 1. Initialize Gemini
llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    temperature=0.4
)

# 2. Unwrap raw functions from FastMCP's FunctionTool wrapper
_initialize_incident_fn = initialize_incident.fn
_add_evidence_fn = add_evidence.fn
_add_recovery_steps_fn = add_recovery_steps.fn
_calculate_risk_score_fn = calculate_risk_score.fn
_finalize_incident_fn = finalize_incident.fn
_get_service_dependencies_fn = get_service_dependencies.fn
_get_blast_radius_fn = get_blast_radius.fn
_get_infrastructure_routes_fn = get_infrastructure_routes.fn

# 3. Plain Python wrappers (callable by LangChain)
def _initialize_incident(incident_id: str, app_id: str = "", initial_summary: str = "") -> str:
    return _initialize_incident_fn(incident_id=incident_id, app_id=app_id, initial_summary=initial_summary)

def _get_service_dependencies(app_id: str) -> str:
    return _get_service_dependencies_fn(app_id=app_id)

def _get_blast_radius(resource_id: str) -> str:
    return _get_blast_radius_fn(resource_id=resource_id)

def _get_infrastructure_routes(app_id: str) -> str:
    return _get_infrastructure_routes_fn(app_id=app_id)

def _add_evidence(incident_id: str, evidence_items: List[Dict[str, Any]]) -> str:
    return _add_evidence_fn(incident_id=incident_id, evidence_items=evidence_items)

def _add_recovery_steps(incident_id: str, steps: List[Dict[str, Any]]) -> str:
    return _add_recovery_steps_fn(incident_id=incident_id, steps=steps)

def _calculate_risk_score(plan_text: str) -> int:
    return _calculate_risk_score_fn(plan_text=plan_text)
def _finalize_incident(
    incident_id: str,
    recovery_plan: str,
    risk_score: int,
    agent_notes: str,
    app_id: str = ""
) -> str:
    return _finalize_incident_fn(
        incident_id=incident_id,
        recovery_plan=recovery_plan,
        risk_score=risk_score,
        agent_notes=agent_notes,
        app_id=app_id
    )

# 4. Wrap as LangChain StructuredTools
tools = [
    StructuredTool.from_function(
        func=_initialize_incident,
        name="initialize_incident",
        description="Creates a new incident record with ANALYZING status. Call this FIRST before any other tool."
    ),
    StructuredTool.from_function(
        func=_get_service_dependencies,
        name="get_service_dependencies",
        description=(
            "Fetches the 2-hop service dependency map for an app from Neo4j. "
            "Returns node types (Service/Database/Infrastructure), relationship types, and edge properties "
            "(pool_size, latency_slo_ms, use_case). Call this right after initialize_incident."
        )
    ),
    StructuredTool.from_function(
        func=_get_blast_radius,
        name="get_blast_radius",
        description=(
            "Given a suspected failing resource ID (e.g. 'payment-db', 'redis-cache'), returns ALL services "
            "across ALL apps that depend on it. Use this when a shared DB or infra node is the suspected root cause."
        )
    ),
    StructuredTool.from_function(
        func=_get_infrastructure_routes,
        name="get_infrastructure_routes",
        description=(
            "Returns the infrastructure (gateways, load balancers) routing traffic into this app's services. "
            "Use this when logs show 502/504 errors or gateway timeouts."
        )
    ),
    StructuredTool.from_function(
        func=_add_evidence,
        name="add_evidence",
        description="Adds evidence log lines to an existing incident. evidence_items: list of dicts with keys: log_line, source (app/db/infra/monitoring), timestamp (ISO string), reasoning."
    ),
    StructuredTool.from_function(
        func=_add_recovery_steps,
        name="add_recovery_steps",
        description="Saves recovery steps to an existing incident. steps: list of dicts with keys: step_order (int), step_description, risk_level (HIGH/MEDIUM/LOW)."
    ),
    StructuredTool.from_function(
        func=_calculate_risk_score,
        name="calculate_risk_score",
        description="Calculates risk score (0-100) for a recovery plan based on dangerous keywords. Pass the full plan text."
    ),
    StructuredTool.from_function(
        func=_finalize_incident,
        name="finalize_incident",
        description="Finalizes the incident ticket, sets status to OPEN. Call this LAST after evidence and recovery steps are saved."
    ),
]

# 5. Bind tools to LLM
llm_with_tools = llm.bind_tools(tools)

# 6. System Prompt
SYSTEM_PROMPT = """You are an expert SRE Agent. Your job is to analyze logs, cross-reference them with system topology, find the root cause, and create a ticket.

### WORKFLOW (MUST FOLLOW IN ORDER):

1. **Initialize Incident**:
   - Call `initialize_incident(incident_id, app_id, initial_summary)` FIRST.

2. **Understand the Architecture** (use all 3 graph tools, in this order):
   a. `get_service_dependencies(app_id)` — maps the full 2-hop dependency chain. Identifies which databases, caches, and queues each service relies on, plus edge properties like pool_size and latency SLOs.
   b. `get_blast_radius(resource_id)` — call this for any resource that looks like a root cause (e.g. a saturated DB or a failing cache). Returns all services across ALL apps affected by it.
   c. `get_infrastructure_routes(app_id)` — call this if the logs show 502/504 errors or gateway timeouts. Maps which gateways sit in front of each service.

3. **Save Evidence**:
   - Call `add_evidence(incident_id, evidence_items)` with all relevant log lines.
   - The log entries include a `service_id` field that maps directly to node IDs in the graph — use this to cite graph context in your reasoning field.
   - Include ALL log lines that form the causal chain.

4. **Analyze & Create Recovery Plan**:
   - Use the topology to make the plan precise (e.g. reference the specific pool_size, max_conn, or timeout_ms from the graph).
   - Call `add_recovery_steps(incident_id, steps)` with ordered, actionable steps.

5. **Calculate Risk Score**:
   - Call `calculate_risk_score(plan_text)` on the full plan text.

6. **Finalize Ticket**:
   - Call `finalize_incident(incident_id, recovery_plan, risk_score, agent_notes, app_id)` LAST.
   - Use the SAME incident_id and app_id throughout.

### LOG FORMAT:
Logs are structured JSON arrays with fields: timestamp, level, service_id, message, metadata.
The `service_id` field maps directly to node IDs in Neo4j — use it to run graph lookups.

### IMPORTANT:
- ALWAYS call `initialize_incident` first.
- ALWAYS call `get_service_dependencies` after initialization.
- Use `get_blast_radius` whenever a shared resource (DB, cache, queue) is suspected.
- Use `get_infrastructure_routes` whenever infra/gateway errors appear in the logs.

"""

# 7. Agent Node
def agent_node(state: AgentState):
    messages = state["messages"]

    if not messages or not isinstance(messages[0], SystemMessage):
        messages = [SystemMessage(content=SYSTEM_PROMPT)] + list(messages)

    response = llm_with_tools.invoke(messages)
    return {"messages": [response]}

# 8. Build the Graph
workflow = StateGraph(AgentState)

workflow.add_node("agent", agent_node)
workflow.add_node("tools", ToolNode(tools))

workflow.set_entry_point("agent")
workflow.add_conditional_edges("agent", tools_condition)
workflow.add_edge("tools", "agent")

app = workflow.compile()