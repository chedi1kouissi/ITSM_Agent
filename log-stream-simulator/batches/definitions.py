import random
from simulator.batch_engine import BatchEngine

def run_batch_001_db_timeout():
    engine = BatchEngine("batch_001_database_timeout", "2026-02-05T10:00:00Z")
    
    # Metadata
    engine.set_metadata({
        "incident_id": "INC-001",
        "title": "Database Timeout Causing Payment Service Failure",
        "root_cause": "database_connection_exhaustion",
        "affected_service": "payment-api",
        "severity": "high",
        "timeline": [
            {"phase": "normal", "start": "10:00:00"},
            {"phase": "degradation", "start": "10:02:00"},
            {"phase": "incident", "start": "10:05:00"},
            {"phase": "recovery", "start": "10:08:00"}
        ]
    })

    # Timeline Execution
    svc = "payment-api"
    
    # 10:00:00 - 10:02:00 NORMAL
    print(f"Generating Batch 001 - Normal Phase...")
    for _ in range(20): # Simulate some ticks
        engine.tick(random.randint(2, 6))
        engine.generate_nominal_requests(svc, latency_base=35)

    # 10:02:00 DEGRADATION start
    # Jump to exact time if needed, or just flow naturally. 
    # For strict compliance with user request, we can set time, but let's flow.
    
    # 10:02:05
    engine.app.log(engine.get_time(), "WARN", svc, "Slow database query", latency="1200ms", request_id="req_101")
    engine.db.log(engine.get_time(), "WARNING", "Slow query", execution_time="3.2s", query='"SELECT * FROM payments"')
    
    engine.tick(25)
    engine.monitor.alert(engine.get_time(), "DatabaseLatencyHigh", "payment-db", latency_ms=1400, threshold=800)
    
    engine.tick(2)
    engine.app.log(engine.get_time(), "WARN", svc, "Slow database query", latency="1850ms", request_id="req_104")
    
    # ... more degradation ...
    engine.tick(120) 
    
    # 10:04:55
    engine.db.log(engine.get_time(), "WARNING", "Connection usage high", active_connections=145, max=150)
    
    engine.tick(10)
    # 10:05:05 INCIDENT
    engine.monitor.alert(engine.get_time(), "ErrorRateSpike", svc, error_rate="32%", threshold="10%")
    
    engine.tick(3)
    engine.db.log(engine.get_time(), "ERROR", "Connection pool exhausted", active_connections=150, max=150)
    
    engine.tick(1)
    engine.db.log(engine.get_time(), "ERROR", "Query timeout", execution_time="7.8s")
    
    engine.tick(1) # 10:05:10
    engine.app.log(engine.get_time(), "ERROR", svc, "Database timeout", request_id="req_210", latency="5200ms")
    
    engine.tick(2)
    engine.app.log(engine.get_time(), "ERROR", svc, "Failed to process payment", error="db_timeout")
    
    engine.tick(18)
    engine.monitor.alert(engine.get_time(), "ServiceDown", svc, instances=0)

    engine.tick(10) # 10:05:40
    engine.app.log(engine.get_time(), "ERROR", svc, "Unhandled exception ConnectionPoolExhausted")
    
    engine.tick(5)
    engine.infra.log(engine.get_time(), "kubelet", f"Pod {svc}-7f8c9 memory usage high 92%")
    
    engine.tick(2)
    engine.infra.log(engine.get_time(), "kubelet", f"Container {svc} restarted", exit_code=137)
    
    engine.tick(13) # 10:06:00
    engine.infra.log(engine.get_time(), "kubelet", f"Liveness probe failed for {svc}")
    
    engine.tick(2)
    engine.app.log(engine.get_time(), "ERROR", svc, "Service unavailable returning 503")

    # RECOVERY 10:08:00
    engine.tick(120)
    
    engine.db.log(engine.get_time(), "INFO", "Connections normalized", active_connections=45)
    
    engine.tick(5)
    engine.infra.log(engine.get_time(), "kubelet", f"Pod {svc}-7f8c9 started successfully")
    
    engine.tick(5)
    engine.app.log(engine.get_time(), "INFO", svc, "Service restarted successfully")
    
    engine.tick(5)
    engine.app.log(engine.get_time(), "INFO", svc, "Request completed", status=200, latency="50ms")
    engine.monitor.alert(engine.get_time(), "RecoveryDetected", svc, error_rate="2%")


def run_batch_002_memory_leak():
    engine = BatchEngine("batch_002_memory_leak", "2026-02-05T11:00:00Z")
    svc = "inventory-api"
    
    engine.set_metadata({
        "incident_id": "INC-002",
        "title": "Inventory Service Memory Leak",
        "root_cause": "memory_leak",
        "affected_service": svc,
        "severity": "high"
    })
    
    # Normal
    engine.generate_nominal_requests(svc, count=10)
    
    # 11:02:12
    engine.tick(130)
    engine.app.log(engine.get_time(), "WARN", svc, "Cache size growing unexpectedly", size_mb=850)
    
    # 11:03:00
    engine.tick(48)
    engine.monitor.alert(engine.get_time(), "HighMemory", svc, memory="92%")
    
    # 11:03:20
    engine.tick(20)
    engine.app.log(engine.get_time(), "WARN", svc, "High memory usage detected", usage_mb=1500)
    
    # 11:04:40
    engine.tick(80)
    engine.infra.log(engine.get_time(), "kubelet", f"Container {svc} memory usage 96%")
    
    engine.tick(4) # 04:44
    engine.infra.log(engine.get_time(), "kubelet", f"Container {svc} terminated", reason="OOMKilled")
    
    engine.tick(1) # 04:45
    engine.app.log(engine.get_time(), "ERROR", svc, "OutOfMemoryError allocation failed")
    
    engine.tick(5) # 04:50
    engine.monitor.alert(engine.get_time(), "ServiceRestartDetected", svc)
    
    engine.tick(10) # 05:00
    engine.infra.log(engine.get_time(), "kubelet", f"Pod {svc} started")
    
    engine.tick(2) # 05:02
    engine.app.log(engine.get_time(), "INFO", svc, "Service started")
    
    engine.tick(18)
    engine.app.log(engine.get_time(), "INFO", svc, "Request completed", status=200, latency="45ms")
    
    engine.tick(10)
    engine.monitor.alert(engine.get_time(), "MemoryNormalized", svc, memory="45%")

def run_batch_003_downstream():
    engine = BatchEngine("batch_003_downstream_api_failure", "2026-02-05T12:00:00Z")
    svc = "payment-api"
    prov = "payment-provider"
    
    engine.set_metadata({
        "incident_id": "INC-003",
        "title": "External Payment Provider Failure",
        "root_cause": "downstream_api_timeout",
        "affected_service": svc,
        "severity": "high"
    })
    
    engine.app.log(engine.get_time(), "INFO", svc, "Payment processed", latency="300ms")
    
    engine.tick(135) # 12:02:15
    engine.app.log(engine.get_time(), "WARN", svc, "External API slow", latency="2500ms")
    
    engine.tick(15) # 12:02:30
    engine.monitor.alert(engine.get_time(), "ExternalDependencyLatency", prov, latency="3200ms")
    
    engine.tick(52) # 12:03:22
    engine.app.log(engine.get_time(), "ERROR", svc, "Payment failed upstream timeout")
    
    engine.tick(8) # 12:03:30
    engine.infra.log(engine.get_time(), "gateway", "Upstream timeout", target=prov)
    
    engine.tick(5) # 12:03:35
    engine.monitor.alert(engine.get_time(), "ErrorRateSpike", svc, error_rate="28%")
    
    engine.tick(5) # 12:03:40
    engine.app.log(engine.get_time(), "ERROR", svc, "Retry attempt failed", request_id="req_502")
    
    engine.tick(2) # 12:03:42
    engine.infra.log(engine.get_time(), "gateway", "HTTP 502 upstream failure", target=prov)

    # 12:06:10
    engine.tick(148)
    engine.app.log(engine.get_time(), "INFO", svc, "External API responding normally")
    
    engine.tick(5)
    engine.monitor.alert(engine.get_time(), "DependencyRecovered", prov)

def run_batch_004_disk_full():
    engine = BatchEngine("batch_004_disk_full", "2026-02-05T13:00:00Z")
    svc = "orders-api"
    node = "prod-node-2"
    
    engine.set_metadata({
        "incident_id": "INC-004",
        "title": "Disk Full on Orders Service Node",
        "root_cause": "disk_full",
        "affected_service": svc,
        "severity": "medium"
    })
    
    engine.app.log(engine.get_time(), "INFO", svc, "Order created", status=201)
    
    engine.tick(129) # 13:02:10
    engine.app.log(engine.get_time(), "WARN", svc, "Write latency increased")
    
    engine.tick(35) # 13:02:45
    engine.monitor.alert(engine.get_time(), "DiskUsageHigh", node=node, usage="95%")
    
    engine.tick(45) # 13:03:30
    engine.infra.log(engine.get_time(), "node", "disk usage 98%", mount="/var/lib/data")
    
    engine.tick(5) # 13:03:35
    engine.infra.log(engine.get_time(), "kernel", "write failure disk full")
    
    engine.tick(5) # 13:03:40
    engine.app.log(engine.get_time(), "ERROR", svc, "Failed to write file", error="no_space_left")
    
    engine.tick(10) # 13:03:50
    engine.monitor.alert(engine.get_time(), "WriteErrorsDetected", svc)
    
    engine.tick(22) # 13:04:12
    engine.app.log(engine.get_time(), "ERROR", svc, "Unable to persist order storage failure")
    
    # 13:06:00
    engine.tick(108)
    engine.infra.log(engine.get_time(), "node", "disk cleanup completed", usage="65%")
    
    engine.tick(20) # 13:06:20
    engine.monitor.alert(engine.get_time(), "DiskUsageNormal", node=node, usage="60%")
    
    engine.tick(10) # 13:06:30
    engine.app.log(engine.get_time(), "INFO", svc, "Write operations restored")
