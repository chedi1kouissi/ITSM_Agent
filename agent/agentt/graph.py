import os
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode, tools_condition
from langchain_core.messages import SystemMessage, HumanMessage

# Import our custom modules
from agentt.state import AgentState
from agentt.tools import create_incident_with_evidence, calculate_risk_score, finalize_itsm_ticket

# Load Environment Variables
load_dotenv()

# 1. Initialize Gemini
llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    temperature=0.4
)

# 2. Bind Tools to the LLM
tools = [create_incident_with_evidence, calculate_risk_score, finalize_itsm_ticket]
llm_with_tools = llm.bind_tools(tools)

# 3. Define the System Prompt
SYSTEM_PROMPT = """You are an expert SRE Agent. Your job is to analyze logs, find the root cause, and create a ticket.

### WORKFLOW (MUST FOLLOW IN ORDER):
1. **Create Incident + Save Evidence FIRST**: 
   - Use `create_incident_with_evidence(incident_id, evidence_items, initial_summary)` as your FIRST action
   - This creates the incident AND saves all relevant log lines that prove the root cause
   - evidence_items format: [{"log_line": "...", "source": "app/db/infra/monitoring", "timestamp": "...", "reasoning": "..."}]
   - The incident_id will be provided to you in the input

2. **Analyze & Create Recovery Plan**: 
   - Based on the evidence, formulate a detailed recovery plan
   - Your plan should be specific, actionable, and safe

3. **Calculate Risk Score**: 
   - Use `calculate_risk_score(plan_text)` to evaluate the risk level (0-100) of your recovery plan

4. **Finalize Ticket**: 
   - Use `finalize_itsm_ticket(incident_id, recovery_plan, risk_score, agent_notes)` to complete the ticket
   - agent_notes should contain your analysis summary and reasoning

### LOG FORMAT:
The logs are provided as a JSON object with 'app_logs', 'database_logs', etc. Cross-reference timestamps to find the causal chain!

### IMPORTANT:
- You MUST call `create_incident_with_evidence` BEFORE `finalize_itsm_ticket`
- Use the SAME incident_id for all tool calls
- Be thorough in identifying evidence - include all relevant log lines
"""

# 4. Define the Node: "Reasoning"
def agent_node(state: AgentState):
    messages = state["messages"]
    
    # If this is the first step, add the System Prompt
    if len(messages) == 0:
        messages = [SystemMessage(content=SYSTEM_PROMPT)]
    
    # Invoke Gemini
    response = llm_with_tools.invoke(messages)
    
    # Return the new message to update the state
    return {"messages": [response]}

# 5. Build the Graph
workflow = StateGraph(AgentState)

# Add Nodes
workflow.add_node("agent", agent_node)
workflow.add_node("tools", ToolNode(tools))

# Add Edges
workflow.set_entry_point("agent")

# conditional_edges checks: Did the agent call a tool? 
# If YES -> go to "tools". If NO -> go to END.
workflow.add_conditional_edges(
    "agent",
    tools_condition,
)

# From "tools" always go back to "agent" (to read the tool output)
workflow.add_edge("tools", "agent")

# Compile the graph
app = workflow.compile()