#main.py
import json
import uuid
import os
from datetime import datetime, timezone
from agentt.graph import app
from langfuse import Langfuse
from langfuse.callback import CallbackHandler
from dotenv import load_dotenv
load_dotenv()

langfuse = Langfuse(host="https://cloud.langfuse.com")
langfuse_handler = CallbackHandler(host="https://cloud.langfuse.com")

RUN_LOGS_DIR = "data/run_logs"


def generate_incident_id():
    year = datetime.now().year
    unique_suffix = str(uuid.uuid4())[:8].upper()
    return f"INC-{year}-{unique_suffix}"


def extract_reasoning(msg) -> str | None:
    """ 
    Gemini returns reasoning text in different places depending on whether
    it also emits tool calls in the same response. Check all of them.
    """
    candidates = []

    # 1. Standard content field (string or list of blocks)
    content = getattr(msg, "content", None)
    if isinstance(content, str) and content.strip():
        candidates.append(content.strip())
    elif isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                t = block.get("text", "").strip()
                if t:
                    candidates.append(t)

    # 2. Gemini sometimes puts a preamble in additional_kwargs["content"]
    #    or inside response_metadata
    additional = getattr(msg, "additional_kwargs", {}) or {}
    for key in ("content", "text", "preamble"):
        val = additional.get(key, "")
        if isinstance(val, str) and val.strip():
            candidates.append(val.strip())

    # 3. response_metadata (varies by SDK version)
    meta = getattr(msg, "response_metadata", {}) or {}
    for key in ("content", "text", "thinking"):
        val = meta.get(key, "")
        if isinstance(val, str) and val.strip():
            candidates.append(val.strip())

    # 4. Some SDK versions expose .text directly
    text_attr = getattr(msg, "text", None)
    if isinstance(text_attr, str) and text_attr.strip():
        candidates.append(text_attr.strip())

    # Deduplicate while preserving order
    seen, unique = set(), []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            unique.append(c)

    return "\n\n".join(unique) if unique else None


def print_reasoning(reasoning: str, max_lines: int = 6) -> None:
    """Pretty-print reasoning, capped to max_lines to avoid wall-of-text."""
    lines = reasoning.splitlines()
    for line in lines[:max_lines]:
        print(f"│   💭 {line}")
    if len(lines) > max_lines:
        print(f"│   💭 ... ({len(lines) - max_lines} more lines — see run log)")


def run_agent():
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

    incident_id = raw_logs_data.get("incident_id") or generate_incident_id()
    app_id = raw_logs_data.get("app_id", "")

    print(f"🎫 Incident ID: {incident_id}")
    print(f"📱 App ID: {app_id}")
    print(f"✅ Logs loaded successfully ({len(raw_logs_str)} characters)")
    print("🤖 Initializing Agent...")
    print("=" * 60)

    trace = langfuse.trace(
        name="itsm-agent-run",
        id=incident_id,
        input={"incident_id": incident_id, "app_id": app_id},
        tags=["itsm", "agent"],
        metadata={"app_id": app_id}
    )
    langfuse_handler.trace_id = trace.id

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
        for event in app.stream(
            initial_state,
            config={"callbacks": [langfuse_handler]}
        ):
            for key, value in event.items():
                print(f"┌─ Node: {key} " + "─" * (50 - len(key)))

                span = trace.span(name=f"node:{key}", metadata={"node": key})

                event_entry = {
                    "node": key,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "tool_calls": [],
                    "llm_reasoning": None,
                    "response_preview": None
                }

                if "messages" in value:
                    last_msg = value["messages"][-1]

                    # ── Reasoning ─────────────────────────────────────────────
                    reasoning = extract_reasoning(last_msg)
                    if reasoning:
                        event_entry["llm_reasoning"] = reasoning[:2000]

                        # Only print reasoning on agent nodes (not tool result nodes)
                        if key == "agent":
                            print("│ 🧠 Reasoning:")
                            print_reasoning(reasoning)

                    # ── Tool calls ────────────────────────────────────────────
                    tool_calls = getattr(last_msg, "tool_calls", []) or []
                    for tc in tool_calls:
                        name = tc.get("name", "?")
                        args = tc.get("args", {})
                        print(f"│ 🔧 Tool Call: {name}")

                        # Print key args inline — skip bulky payloads
                        skip_keys = {"evidence_items", "steps", "plan_text", "recovery_plan"}
                        brief = {k: v for k, v in args.items() if k not in skip_keys}
                        if brief:
                            print(f"│    args: {json.dumps(brief, ensure_ascii=False)[:120]}")

                        event_entry["tool_calls"].append({"name": name, "args": args})

                    # ── Tool result (tools node) ───────────────────────────────
                    if key == "tools" and hasattr(last_msg, "name"):
                        result_content = str(last_msg.content)
                        tool_result = {
                            "tool_name": getattr(last_msg, "name", None),
                            "content": result_content[:1000]
                        }
                        event_entry["tool_result"] = tool_result
                        span.update(output=tool_result)

                        # Print a compact preview
                        preview = result_content[:200]
                        suffix = "..." if len(result_content) > 200 else ""
                        print(f"│ 💬 Response: {preview}{suffix}")

                    # ── Final text response (no tool calls) ───────────────────
                    if not tool_calls and key == "agent" and reasoning:
                        preview = reasoning[:300]
                        suffix = "..." if len(reasoning) > 300 else ""
                        print(f"│ 💬 Response: {preview}{suffix}")
                        event_entry["response_preview"] = reasoning[:1000]

                span.end(output={
                    "tool_calls": event_entry["tool_calls"],
                    "llm_reasoning": event_entry["llm_reasoning"]
                })

                print("└" + "─" * 56)
                print()

                run_log["events"].append(event_entry)

        run_log["status"] = "completed"
        trace.update(
            output={"status": "completed", "incident_id": incident_id},
            metadata={"total_nodes": len(run_log["events"])}
        )

        print("=" * 60)
        print(f"✅ Agent execution completed for {incident_id}")
        print("=" * 60)

        # ── Debug helper: dump all reasoning entries ──────────────────────────
        reasoning_entries = [
            e for e in run_log["events"] if e.get("llm_reasoning")
        ]
        if not reasoning_entries:
            print(
                "\n⚠️  No reasoning text was captured. "
                "This usually means Gemini returned only tool calls with no preamble text.\n"
                "   → Try adding 'Think step by step before calling any tool.' to your system prompt.\n"
                "   → Or enable Gemini's thinking mode if available in your SDK version."
            )

    except Exception as e:
        run_log["status"] = "failed"
        run_log["error"] = str(e)
        trace.update(output={"status": "failed", "error": str(e)}, level="ERROR")
        print(f"❌ Error during execution: {str(e)}")
        import traceback
        traceback.print_exc()

    finally:
        run_log["finished_at"] = datetime.now(timezone.utc).isoformat()
        langfuse.flush()

        os.makedirs(RUN_LOGS_DIR, exist_ok=True)
        log_output_path = os.path.join(RUN_LOGS_DIR, f"{incident_id}.json")
        with open(log_output_path, "w") as f:
            json.dump(run_log, f, indent=2)
        print(f"\n📝 Run log written to: {log_output_path}")


if __name__ == "__main__":
    run_agent()