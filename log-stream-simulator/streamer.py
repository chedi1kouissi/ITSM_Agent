"""
Streamer for ITSM Agent Log Simulator
=========================================
Reads a generated raw JSON batch file and emits the logs to stdout
as JSON Lines (NDJSON), simulating real-time progression based on timestamps.
"""

import os
import sys
import json
import time
import argparse
from datetime import datetime

def parse_iso_time(timestamp_str: str) -> datetime:
    # Handle Python 3.10 datetime parsing
    return datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))

def stream_logs(filepath: str, speed: float):
    if not os.path.exists(filepath):
        print(f"Error: File '{filepath}' not found.", file=sys.stderr)
        sys.exit(1)

    print(f"[*] Loading raw batch from {filepath}...", file=sys.stderr)
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            batch_data = json.load(f)
    except Exception as e:
        print(f"Error reading JSON: {e}", file=sys.stderr)
        sys.exit(1)

    logs = batch_data.get("logs", [])
    if not logs:
        print("No logs found in batch.", file=sys.stderr)
        return

    print(f"[*] Found {len(logs)} logs. Streaming at {speed}x speed...", file=sys.stderr)
    
    # Also pass along the app_id and incident_id for context if needed by the listener
    # We can emit a special control message first
    control_msg = {
        "_type": "control",
        "app_id": batch_data.get("app_id"),
        "incident_id": batch_data.get("incident_id"),
        "scenario_title": batch_data.get("scenario_title")
    }
    print(json.dumps(control_msg), flush=True)

    previous_time = None

    for log in logs:
        try:
            current_time = parse_iso_time(log["timestamp"])
            
            if previous_time is not None:
                # Calculate real-world seconds between logs
                delta_seconds = (current_time - previous_time).total_seconds()
                
                # If logs are out of order, delta_seconds might be negative, safeguard against it
                if delta_seconds > 0:
                    sleep_time = delta_seconds / speed
                    time.sleep(sleep_time)

            log["_type"] = "log"
            # Emit as JSON Line
            print(json.dumps(log), flush=True)
            
            previous_time = current_time

        except Exception as e:
            print(f"Error parsing log: {e}. Skipping.", file=sys.stderr)

    print(f"[*] Streaming complete.", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description="Simulate real-time log streaming from a JSON batch.")
    parser.add_argument("--file", "-f", required=True, help="Path to raw_batch_*.json file")
    parser.add_argument("--speed", "-s", type=float, default=1.0, help="Speed multiplier (e.g., 2.0 for 2x faster). Default: 1.0")
    
    args = parser.parse_args()
    stream_logs(args.file, args.speed)

if __name__ == "__main__":
    main()
