import os
import json
import random
import datetime
from simulator.components import AppLogger, InfraLogger, MonitorLogger, DBLogger

class BatchEngine:
    def __init__(self, batch_name, start_time_str="2026-02-05T10:00:00Z"):
        self.batch_name = batch_name
        self.output_dir = os.path.join("generated_batches", batch_name)
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)
            
        # Parse start time
        # Support Z or offset is a bit tricky with pure strptime, keeping it simple for now
        self.current_time = datetime.datetime.strptime(start_time_str.replace("Z", ""), "%Y-%m-%dT%H:%M:%S")
        
        self.app = AppLogger(self.output_dir)
        self.infra = InfraLogger(self.output_dir)
        self.monitor = MonitorLogger(self.output_dir)
        self.db = DBLogger(self.output_dir)
        
        self.metadata = {}

    def set_metadata(self, meta):
        self.metadata = meta
        with open(os.path.join(self.output_dir, "metadata.json"), "w") as f:
            json.dump(meta, f, indent=2)

    def tick(self, seconds):
        self.current_time += datetime.timedelta(seconds=seconds)
    
    def get_time(self):
        return self.current_time

    # --- NOISE GENERATORS ---
    def generate_nominal_requests(self, service, count=1, latency_base=30):
        for _ in range(count):
            lat = int(random.gauss(latency_base, 5))
            self.app.log(self.current_time, "INFO", service, "Request completed", status=200, latency=f"{lat}ms")

