import json
import uuid
import os
from datetime import datetime, timezone
from agentt.graph import app

RUN_LOGS_DIR = "data/run_logs"


def generate_incident_id():
    """Generates a unique incident ID in format: INC-YYYY-XXXX"""
    year = datetime.now().year
    unique_suffix = str(uuid.uuid4())[:8].upper()
    return f"INC-{year}-{unique_suffix}"


def run_agent():
    # 1. Load the Log Batch FIRST (incident_id and app_id come from the file)
    log_file_path = "data/logs.json"

    print(f"📂 Loading logs from {log_file_path}...")
    try:
        with open(log_file_path, "r") as f:
            raw_logs_data = json.load(f)
            raw_logs_str = json.dumps(raw_logs_data, indent=2)
    except FileNotFoundError:
        print("❌ Error: data/logs.json not found!")
        return
    except json.JSONDecodeError:
        print("❌ Error: Invalid JSON in logs.json!")
        return

    # 2. Extract incident_id and app_id from the log batch
    incident_id = raw_logs_data.get("incident_id") or generate_incident_id()
    app_id = raw_logs_data.get("app_id", "")

    print(f"🎫 Incident ID: {incident_id}")
    print(f"📱 App ID: {app_id}")
    print(f"✅ Logs loaded successfully ({len(raw_logs_str)} characters)")
    print("🤖 Initializing Agent...")
    print("="*60)

    # 3. Define Initial State
    initial_state = {
        "messages": [
            ("user", f"""Incident ID: {incident_id}
App ID: {app_id}

Please analyze the following log batch and create a complete incident ticket.

LOG DATA:
{raw_logs_str}

Instructions:
1. Identify the root cause by analyzing timestamps and error patterns
2. Extract specific log lines as evidence
3. Create a detailed recovery plan with clear steps
4. Calculate the risk score
5. Save everything to the database using the appropriate tools in order

Use incident_id="{incident_id}" and app_id="{app_id}" for ALL database operations.
""")
        ],
        "raw_logs": raw_logs_str,
        "evidence_chain": [],
        "ticket_status": "analyzing"
    }

    # 4. Run the Graph and capture a full run log
    print("\n🔄 Starting Agent Execution...\n")

    run_log = {
        "incident_id": incident_id,
        "app_id": app_id,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "finished_at": None,
        "status": "running",
        "events": []
    }

    try:
        for event in app.stream(initial_state):
            for key, value in event.items():
                print(f"┌─ Node: {key} " + "─"*(50 - len(key)))

                event_entry = {
                    "node": key,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "tool_calls": [],
                    "llm_reasoning": None,    # LLM thought text (even during tool calls)
                    "response_preview": None  # Final response text (no tool calls)
                }

                if "messages" in value:
                    last_msg = value["messages"][-1]

                    # Always capture any text content the LLM produced (reasoning)
                    if hasattr(last_msg, "content") and last_msg.content:
                        content = last_msg.content
                        # content can be a list of dicts (Gemini) or a plain string
                        if isinstance(content, list):
                            text_parts = [
                                p.get("text", "") for p in content
                                if isinstance(p, dict) and p.get("type") == "text"
                            ]
                            content_str = " ".join(text_parts).strip()
                        else:
                            content_str = str(content).strip()

                        if content_str:
                            event_entry["llm_reasoning"] = content_str[:1000]

                    if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
                        for tool_call in last_msg.tool_calls:
                            print(f"│ 🔧 Tool Call: {tool_call['name']}")
                            event_entry["tool_calls"].append({
                                "name": tool_call["name"],
                                "args": tool_call.get("args", {})
                            })
                    elif hasattr(last_msg, "content") and last_msg.content:
                        # Pure response (no tool call) — store as preview too
                        if event_entry["llm_reasoning"]:
                            preview = event_entry["llm_reasoning"]
                            if len(str(last_msg.content)) > 200:
                                print(f"│ 💬 Response: {str(last_msg.content)[:200]}...")
                            else:
                                print(f"│ 💬 Response: {str(last_msg.content)}")
                            event_entry["response_preview"] = preview

                    # Capture tool results only on 'tools' nodes (ToolMessage)
                    if key == "tools" and hasattr(last_msg, "name"):
                        event_entry["tool_result"] = {
                            "tool_name": getattr(last_msg, "name", None),
                            "content": str(last_msg.content)[:1000]
                        }

                print("└" + "─"*56)
                print()

                run_log["events"].append(event_entry)

        run_log["status"] = "completed"
        print("="*60)
        print(f"✅ Agent execution completed for {incident_id}")
        print("="*60)

    except Exception as e:
        run_log["status"] = "failed"
        run_log["error"] = str(e)
        print(f"❌ Error during execution: {str(e)}")
        import traceback
        traceback.print_exc()

    finally:
        run_log["finished_at"] = datetime.now(timezone.utc).isoformat()

        # 5. Write run log to data/run_logs/<incident_id>.json
        os.makedirs(RUN_LOGS_DIR, exist_ok=True)
        log_output_path = os.path.join(RUN_LOGS_DIR, f"{incident_id}.json")
        with open(log_output_path, "w") as f:
            json.dump(run_log, f, indent=2)
        print(f"\n📝 Run log written to: {log_output_path}")


if __name__ == "__main__":
    run_agent()