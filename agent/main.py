import json
import uuid
from datetime import datetime
from agentt.graph import app

def generate_incident_id():
    """Generates a unique incident ID in format: INC-YYYY-XXXX"""
    year = datetime.now().year
    unique_suffix = str(uuid.uuid4())[:8].upper()
    return f"INC-{year}-{unique_suffix}"

def run_agent():
    # 1. Generate Incident ID
    incident_id = generate_incident_id()
    print(f"🎫 Generated Incident ID: {incident_id}")
    
    # 2. Load the Log Batch
    log_file_path = "data/logs.json"
    
    print(f"📂 Loading logs from {log_file_path}...")
    try:
        with open(log_file_path, "r") as f:
            raw_logs_data = json.load(f)
            # Convert dict to formatted string for the LLM
            raw_logs_str = json.dumps(raw_logs_data, indent=2)
    except FileNotFoundError:
        print("❌ Error: data/logs.json not found!")
        return
    except json.JSONDecodeError:
        print("❌ Error: Invalid JSON in logs.json!")
        return

    print(f"✅ Logs loaded successfully ({len(raw_logs_str)} characters)")
    print("🤖 Initializing Agent...")
    print("="*60)

    # 3. Define Initial State
    initial_state = {
        "messages": [
            ("user", f"""Incident ID: {incident_id}

Please analyze the following log batch and create a complete incident ticket.

LOG DATA:
{raw_logs_str}

Instructions:
1. Identify the root cause by analyzing timestamps and error patterns
2. Extract specific log lines as evidence
3. Create a detailed recovery plan with clear steps
4. Calculate the risk score
5. Save everything to the database using the appropriate tool(s)

Use the incident ID: {incident_id} for all database operations.
""")
        ],
        "raw_logs": raw_logs_str,
        "evidence_chain": [],
        "ticket_status": "analyzing"
    }

    # 4. Run the Graph
    print("\n🔄 Starting Agent Execution...\n")
    
    try:
        for event in app.stream(initial_state):
            for key, value in event.items():
                print(f"┌─ Node: {key} " + "─"*(50 - len(key)))
                
                if "messages" in value:
                    last_msg = value["messages"][-1]
                    
                    # Check if it's a tool call
                    if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
                        for tool_call in last_msg.tool_calls:
                            print(f"│ 🔧 Tool Call: {tool_call['name']}")
                            # Optionally print args (can be verbose)
                            # print(f"│ Args: {tool_call['args']}")
                    
                    # Check if it's tool output
                    elif hasattr(last_msg, "content") and last_msg.content:
                        content = str(last_msg.content)
                        # Truncate long content
                        if len(content) > 200:
                            print(f"│ 💬 Response: {content[:200]}...")
                        else:
                            print(f"│ 💬 Response: {content}")
                
                print("└" + "─"*56)
                print()
        
        print("="*60)
        print(f"✅ Agent execution completed for {incident_id}")
        print("="*60)
        
    except Exception as e:
        print(f"❌ Error during execution: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    run_agent()