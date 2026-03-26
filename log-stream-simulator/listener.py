"""
Listener for ITSM Agent Log Simulator
=========================================
Listens to a JSON Lines stream on stdin. Keeps a rolling buffer of logs.
When an incident is detected (e.g., severe errors), it packages the buffer
into the ITSM expected format, saves it, and invokes the ITSM agent.
"""

import sys
import json
import logging
import subprocess
from pathlib import Path
from collections import deque

logging.basicConfig(level=logging.INFO, format='%(asctime)s [LISTENER] %(message)s', datefmt='%H:%M:%S')

# The path where the agent expects the logs
AGENT_DIR = Path(__file__).parent.parent / "agent"
AGENT_DATA_FILE = AGENT_DIR / "data" / "logs.json"

class LogListener:
    def __init__(self, buffer_size=100, error_threshold=3, alert_triggers_immediately=True):
        self.buffer = deque(maxlen=buffer_size)
        
        self.error_threshold = error_threshold
        self.alert_triggers_immediately = alert_triggers_immediately
        
        # Incident contextual info
        self.app_id = "unknown-app"
        self.incident_id = "INC-UNKNOWN"
        self.scenario_title = "Unknown Scenario"
        
        # To prevent triggering multiple times for the same stream
        self.has_triggered = False

    def process_control_message(self, msg):
        """Extracts context from the generator's control message."""
        self.app_id = msg.get("app_id", self.app_id)
        self.incident_id = msg.get("incident_id", self.incident_id)
        self.scenario_title = msg.get("scenario_title", self.scenario_title)
        logging.info(f"Initialized Listener for App: {self.app_id} | Scenario: {self.scenario_title}")

    def process_log(self, log):
        """Processes a single log, appends to buffer, and checks for triggers."""
        # Store log
        self.buffer.append(log)
        
        # Output incoming log for visual tracking
        lvl = log.get("level", "INFO")
        svc = log.get("service_id", "unknown")
        msg = log.get("message", "")
        # Very basic color-coding logic could be added, but standard logging is fine
        if lvl in ["ERROR", "FATAL", "ALERT"]:
            logging.warning(f"{lvl} from {svc}: {msg}")
        else:
            logging.info(f"{svc}: {msg[:60]}...")
            
        if not self.has_triggered:
            self.check_triggers()

    def check_triggers(self):
        """Checks if the buffer contains enough evidence of an incident."""
        error_count = 0
        
        for log in self.buffer:
            lvl = log.get("level", "")
            
            # An explicit monitoring alert or fatal error might trigger immediately
            if self.alert_triggers_immediately and lvl in ["ALERT", "FATAL"]:
                logging.error(f"🚨 CRITICAL EVENT DETECTED ({lvl}). TRIGGERING AGENT!")
                self.trigger_agent()
                return
                
            if lvl == "ERROR":
                error_count += 1
                
        # If we see a burst of errors
        if error_count >= self.error_threshold:
            logging.error(f"🚨 ERROR THRESHOLD REACHED ({error_count} errors). TRIGGERING AGENT!")
            self.trigger_agent()
            return

    def trigger_agent(self):
        """Formats the logs, saves to data/logs.json, and runs the agent."""
        self.has_triggered = True
        
        logging.info(f"Packaging {len(self.buffer)} logs for the ITSM Agent...")
        
        formatted_payload = {
            "app_id": self.app_id,
            "incident_id": self.incident_id,
            "app_logs": [],
            "database_logs": [],
            "infrastructure_logs": [],
            "monitoring_logs": []
        }
        
        # Map logs to the exact buckets the ITSM agent expects
        for log in self.buffer:
            layer = log.get("layer", "")
            # Remove internal keys before sending to agent
            clean_log = {
                "timestamp": log.get("timestamp"),
                "level": log.get("level"),
                "service_id": log.get("service_id"),
                "message": log.get("message"),
                "metadata": log.get("metadata", {})
            }
            
            if layer == "app":
                formatted_payload["app_logs"].append(clean_log)
            elif layer == "database":
                formatted_payload["database_logs"].append(clean_log)
            elif layer == "infrastructure":
                formatted_payload["infrastructure_logs"].append(clean_log)
            elif layer == "monitoring":
                formatted_payload["monitoring_logs"].append(clean_log)
            else:
                # If layer is missing or unknown, try to guess or just put in app
                formatted_payload["app_logs"].append(clean_log)
                
        # Save to the agent's data directory
        AGENT_DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(AGENT_DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(formatted_payload, f, indent=2)
            
        logging.info(f"Saved payload to {AGENT_DATA_FILE}. Invoking Agent...")
        
        # Determine the Python executable to use
        # Prefer the 'itsm' venv inside the agent directory if it exists
        venv_python_win = AGENT_DIR / "itsm" / "Scripts" / "python.exe"
        venv_python_unix = AGENT_DIR / "itsm" / "bin" / "python"
        
        if venv_python_win.exists():
            agent_python = str(venv_python_win)
        elif venv_python_unix.exists():
            agent_python = str(venv_python_unix)
        else:
            agent_python = sys.executable

        # Run the agent in a subprocess
        try:
            # We also pipe stdout/stderr directly so the user sees the agent thinking.
            process = subprocess.Popen(
                [agent_python, "main.py"],
                cwd=str(AGENT_DIR),
                stdout=sys.stdout,
                stderr=sys.stderr
            )
            # We will wait for the agent to finish
            process.wait()
            logging.info(f"ITSM Agent finished with code {process.returncode}")
            
        except Exception as e:
            logging.error(f"Failed to run ITSM Agent: {e}")
            
def main():
    listener = LogListener(buffer_size=100, error_threshold=3)
    
    logging.info("Listening for logs on stdin...")
    
    # Read line by line from standard input
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
            
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
            
        msg_type = msg.get("_type")
        
        if msg_type == "control":
            listener.process_control_message(msg)
        elif msg_type == "log":
            listener.process_log(msg)
            
    if not listener.has_triggered:
        logging.info("Stream ended. No incident detected.")

if __name__ == "__main__":
    main()
