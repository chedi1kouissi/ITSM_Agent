import json
from agentt.graph import app

def run_agent():
    # 1. Load the Log Batch
    log_file_path = "data/logs.json"  # Ensure your file is named logs.json
    
    print(f"Loading logs from {log_file_path}...")
    try:
        with open(log_file_path, "r") as f:
            raw_logs_data = json.load(f)
            # Convert dict to string for the LLM prompt
            raw_logs_str = json.dumps(raw_logs_data, indent=2)
    except FileNotFoundError:
        print("Error: data/logs.json not found!")
        return

    print("Logs loaded. Initializing Agent...")

    # 2. Define Initial State
    initial_state = {
        "messages": [
            ("user", f"Here is the log batch for analysis:\n{raw_logs_str}")
        ],
        "raw_logs": raw_logs_str,
        "evidence_chain": [],
        "ticket_status": "analyzing"
    }

    # 3. Run the Graph
    # The 'stream' method lets us see steps as they happen
    for event in app.stream(initial_state):
        for key, value in event.items():
            print(f"\n--- Node: {key} ---")
            # If it's the agent speaking, print a snippet
            if "messages" in value:
                last_msg = value["messages"][-1]
                if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
                     print(f"Tool Call: {last_msg.tool_calls[0]['name']}")
                else:
                     print(f"Agent Thought: {last_msg.content[:100]}...")

if __name__ == "__main__":
    run_agent()