import os
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode, tools_condition
from langchain_core.messages import SystemMessage, HumanMessage

# Import our custom modules
from agentt.state import AgentState
from agentt.tools import save_relevant_evidence, calculate_risk_score, create_itsm_ticket

# Load Environment Variables
load_dotenv()

# 1. Initialize Gemini
llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    temperature=0.4
)

# 2. Bind Tools to the LLM
tools = [save_relevant_evidence, calculate_risk_score, create_itsm_ticket]
llm_with_tools = llm.bind_tools(tools)

# 3. Define the System Prompt
SYSTEM_PROMPT = """You are an expert SRE Agent. Your job is to analyze logs, find the root cause, and create a ticket.

### INSTRUCTIONS:
1. **Analyze**: Read the `raw_logs` in the input. Look for the causal chain (errors -> failures).
2. **Filter**: Use `save_relevant_evidence` to save the specific log lines that prove the root cause. Explain your reasoning for each.
3. **Plan & Risk**: Formulate a recovery plan. Then, use `calculate_risk_score` to check its safety.
4. **Finalize**: Use `create_itsm_ticket` to save the incident.

### LOG FORMAT:
The logs are provided as a JSON object with 'app_logs', 'database_logs', etc. Cross-reference timestamps!
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