# Realistic Log Generator for Incident Detection (LLM-Powered)

This tool generates **realistic, graph-aware, and correlated log streams** designed to test the AI-powered ITSM Agent. It has recently been upgraded from a static, rule-based batch generator to a dynamic, LLM-powered event-driven architecture using Gemini.

## 🚀 Features

-   **Graph-Aware Generation**: Reads the actual Neo4j infrastructure topology (`seed_graph.cypher`) so all generated logs reflect real services, databases, and structural dependencies.
-   **LLM-Powered Scenarios**: Uses Gemini to autonomously craft tricky incident storylines. Every run produces a unique, chronologically correct incident without manual scripting.
-   **Multi-Layer Correlation**: Events are synchronized across Application, Database, Infrastructure, and Monitoring layers.
-   **Real-Time Streaming**: Emits logs as JSON Lines (NDJSON) observing actual timestamp deltas simulating live traffic.
-   **Intelligent Listener**: Actively monitors the stream, buffers logs, detects critical incident thresholds, and auto-invokes the ITSM Agent with a clean payload.

## 📦 Usage

### Prerequisites
-   Python 3.10+
-   `google-generativeai` installed
-   `dotenv` installed
-   A valid `GEMINI_API_KEY` in the `agent/.env` file.

### Running the Pipeline

The new architecture is broken into three modular scripts. You can run them individually or pipe them together for the full end-to-end experience.

#### 1. Generate an Incident Batch
```bash
python generator.py
```
*What it does:* Reads the Neo4j graph, prompts Gemini for an incident (stopping at the peak with no recovery logs), and saves the raw log array to `generated_logs/raw_batch_INC-YYYY-XXXX.json`.

#### 2. Stream the Logs
```bash
python streamer.py -f generated_logs/raw_batch_INC-YYYY-XXXX.json --speed 1.0
```
*What it does:* Reads the generated batch and emits it to `stdout` line-by-line, sleeping between lines to match the actual timestamp differentials. Use `--speed 50` to speed it up.

#### 3. Run the Full End-to-End Pipeline
Pipe the streamer directly into the listener to watch the system detect the incident and trigger the ITSM agent entirely automatically:

```bash
python streamer.py -f generated_logs/raw_batch_INC-YYYY-XXXX.json --speed 50 | python listener.py
```

*What the listener does:* 
1. Consumes the stream.
2. Keeps a rolling buffer of logs.
3. If it detects a predefined threshold (e.g., 3 ERRORs or 1 ALERT), it packages the buffer into the required ITSM format (`app_logs`, `database_logs`, etc.).
4. Saves it to `../agent/data/logs.json`.
5. Spawns `python main.py` in the `agent` directory to resolve the ticket.

## 🛠️ Components

-   **`generator.py` (The Producer)**: The LLM brain. Contains the strict Pydantic schemas and system prompts ensuring Gemini outputs perfect incident JSON batches.
-   **`streamer.py` (The Broker)**: The time-simulation script. Translates a static JSON array into a live, flowing stream of NDJSON events.
-   **`listener.py` (The Consumer)**: The "PagerDuty" equivalent. Sniffs the stream for anomalies and wakes up the ITSM agent when things break.

*(Note: The legacy rule-based tools, `main.py` and `batches/`, are preserved but the primary path is now this dynamic pipeline).*
