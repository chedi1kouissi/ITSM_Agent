# Realistic Log Generator for Incident Detection

This tool generates **realistic, correlated log batches** designed to test Incident Detection Systems, SIEMs, and SRE dashboards. Unlike simple random log generators, this tool simulates complete "Incident Stories" with a coherent timeline across Application, Database, Infrastructure, and Monitoring layers.

## 🚀 Features

-   **Story-Based Generation**: Logs follow a defined script (Normal -> Degradation -> Failure -> Recovery).
-   **Multi-Layer Correlation**: Events are synchronized across multiple log files.
    -   *Example*: A slow DB query (database.log) causes high App latency (application.log), triggering a Prometheus alert (monitoring.log) and eventually an OOM Kill (infrastructure.log).
-   **Structured Output**: Each run produces a self-contained folder with a `metadata.json` "Answer Key".

## 📦 Usage

### Prerequisites
-   Python 3.6+
-   No external dependencies required (Standard Library only).

### Running the Tool
Open a terminal in the project folder and run:

```bash
# Generate ALL available batches
python main.py --batch all

# Generate a specific batch
python main.py --batch batch_001
python main.py --batch batch_004

# List available batches
python main.py --list
```

### Output
Logs are generated in the `generated_batches/` directory.
Example structure:
```
generated_batches/
└── batch_001_database_timeout/
    ├── metadata.json       # Incident details, root cause, and timeline
    ├── application.log     # API requests, errors, stack traces
    ├── database.log        # Slow queries, connection pool errors
    ├── infrastructure.log  # K8s events, container restarts
    └── monitoring.log      # Simulated alerts (HighLatency, ErrorRateSpike)
```

## 🧪 Included Scenarios

The tool comes with 4 enterprise-grade scenarios:

1.  **Database Timeout (`batch_001`)**: 
    -   Slow queries exhaust the connection pool.
    -   App fails with 503 errors.
    -   Monitoring alerts on high latency.
2.  **Memory Leak (`batch_002`)**:
    -   App memory usage creeps up over time.
    -   Performance degrades.
    -   Infrastructure layer kills the container (OOMKilled).
    -   Service auto-restarts.
3.  **Downstream Failure (`batch_003`)**:
    -   External Payment Provider becomes slow/unresponsive.
    -   Gateway logs 502/504 errors.
    -   App retries fail.
4.  **Disk Full (`batch_004`)**:
    -   Node disk usage hits 98%.
    -   Write operations fail.
    -   Log rotation/cleanup triggers recovery.

## 🛠️ How It Works (Development Guide)

### Core Components
-   **`main.py`**: Entry point. Parses CLI args and dispatches to the batch engine.
-   **`simulator/batch_engine.py`**: The "Director". It maintains a virtual clock (`engine.tick(seconds)`) and holds references to all loggers. It allows scripts to jump forward in time to exact moments.
-   **`simulator/components.py`**: Classes (`AppLogger`, `DBLogger`, etc.) that handle timestamp formatting and writing to files.
-   **`batches/definitions.py`**: **This is where the magic happens.** This file contains the "scripts" for each scenario.

### How to Add a New Batch
1.  Open `batches/definitions.py`.
2.  Define a new function, e.g., `run_batch_005_network_partition()`.
3.  Use the `engine` to tell your story:
    ```python
    def run_batch_005_network_partition():
        engine = BatchEngine("batch_005_network_partition", "2026-03-01T10:00:00Z")
        engine.set_metadata({...})

        # 1. Normal Traffic
        engine.generate_nominal_requests("my-service", count=5)
        
        # 2. Advance time 5 minutes
        engine.tick(300)
        
        # 3. Log an event
        engine.infra.log(engine.get_time(), "network", "Switch port flutter detected")
    ```
4.  Register your function in `main.py` inside the `BATCHES` dictionary.
