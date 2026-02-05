import os
import datetime
import config

class Component:
    def __init__(self, name, output_dir, filename):
        self.name = name
        self.filepath = os.path.join(output_dir, filename)
    
    def write(self, entry):
        with open(self.filepath, "a") as f:
            f.write(entry + "\n")
            
    def fmt_time(self, dt):
        return dt.strftime(config.DATE_FORMAT)

class AppLogger(Component):
    def __init__(self, output_dir):
        super().__init__("App", output_dir, config.FILE_APP)
    
    def log(self, timestamp, level, service, message, **kwargs):
        # 2026-02-05T10:00:01Z INFO payment-api Request completed status=200 latency=35ms
        # kwargs become key=value
        kv_str = " ".join([f"{k}={v}" for k,v in kwargs.items()])
        entry = f"{self.fmt_time(timestamp)} {level} {service} {message} {kv_str}"
        self.write(entry.strip())

class InfraLogger(Component):
    def __init__(self, output_dir):
        super().__init__("Infra", output_dir, config.FILE_INFRA)
    
    def log(self, timestamp, source, message, **kwargs):
        # 2026-02-05T10:05:45Z kubelet Pod payment-api-7f8c9 memory usage high 92%
        kv_str = " ".join([f"{k}={v}" for k,v in kwargs.items()])
        entry = f"{self.fmt_time(timestamp)} {source} {message} {kv_str}"
        self.write(entry.strip())

class MonitorLogger(Component):
    def __init__(self, output_dir):
        super().__init__("Monitor", output_dir, config.FILE_MONITOR)
    
    def alert(self, timestamp, alert_name, service=None, **kwargs):
        # 2026-02-05T10:02:30Z ALERT DatabaseLatencyHigh service=payment-db latency_ms=1400 threshold=800
        kv_str = " ".join([f"{k}={v}" for k,v in kwargs.items()])
        if service:
            entry = f"{self.fmt_time(timestamp)} ALERT {alert_name} service={service} {kv_str}"
        else:
            entry = f"{self.fmt_time(timestamp)} ALERT {alert_name} {kv_str}"
        self.write(entry.strip())

class DBLogger(Component):
    def __init__(self, output_dir):
        super().__init__("DB", output_dir, config.FILE_DB)
    
    def log(self, timestamp, level, message, **kwargs):
        # 2026-02-05T10:02:01Z DB WARNING Slow query execution_time=3.2s query="SELECT ..."
        kv_str = " ".join([f"{k}={v}" for k,v in kwargs.items()])
        entry = f"{self.fmt_time(timestamp)} DB {level} {message} {kv_str}"
        self.write(entry.strip())
