import time
import random
import threading
from simulator.components import LoadBalancer, AppServer, Database
from simulator.generators import get_random_ip, get_random_ua, get_random_user, get_trace_id

class SimulationEngine:
    def __init__(self, duration, rate, scenario_name):
        self.duration = duration
        self.target_rate = rate
        self.scenario_name = scenario_name
        
        # Components
        self.lb = LoadBalancer()
        self.app = AppServer()
        self.db = Database()
        
        self.running = True
        self.start_time = 0

    def run(self):
        self.start_time = time.time()
        print(f"[*] Simulation started. Press Ctrl+C to stop.")
        
        # dynamic import to avoid circular dependency issues if any
        from scenarios.registry import SCENARIOS
        scenario_func = SCENARIOS.get(self.scenario_name)
        
        if not scenario_func:
            print(f"[!] Scenario '{self.scenario_name}' not found. Using 'nominal'.")
            from scenarios.registry import nominal_traffic
            scenario_func = nominal_traffic

        while self.running and (time.time() - self.start_time < self.duration):
            # Calculate how many events to fire this tick
            # Simple implementation: sleep 1/rate
            
            # Execute scenario logic (it decides what to trigger)
            scenario_func(self)
            
            time_to_sleep = 1.0 / self.target_rate
            # Add some jitter
            time.sleep(time_to_sleep * random.uniform(0.8, 1.2))

    # --- ATOMIC FLOWS ---

    def flow_login(self, success=True, delay_ms=None, override_ip=None, override_user=None):
        trace_id = get_trace_id()
        ip = override_ip if override_ip else get_random_ip()
        ua = get_random_ua()
        user = override_user if override_user else (get_random_user() or "unknown_user")
        
        # 1. LB receives request
        self.lb.log_request(ip, "POST", "/api/v1/login", 200, 450, ua, 50)
        
        # 2. App processes
        self.app.log("INFO", trace_id, "Incoming login request", user_id=None, extra={"ip": ip})
        
        if delay_ms:
             time.sleep(delay_ms / 1000.0)

        # 3. DB Check
        q_time = random.uniform(2, 10)
        self.db.log_query(f"SELECT id, password_hash FROM users WHERE username = '{user}'", q_time)
        
        if success:
            self.app.log("INFO", trace_id, "User authenticated successfully", user_id=user)
            self.lb.log_request(ip, "POST", "/api/v1/login", 200, 1200, ua, 40) # Response
        else:
            self.app.log("WARN", trace_id, "Authentication failed: invalid credentials", user_id=user)
            self.lb.log_request(ip, "POST", "/api/v1/login", 401, 80, ua, 40)

    def flow_search_product(self):
        trace_id = get_trace_id()
        ip = get_random_ip()
        ua = get_random_ua()
        user = get_random_user()
        term = random.choice(["laptop", "phone", "shoes", "headphones", "desk"])
        
        self.lb.log_request(ip, "GET", f"/api/v1/products?q={term}", 200, 0, ua, 10)
        self.app.log("INFO", trace_id, f"Search request: '{term}'", user_id=user)
        
        # DB Search
        self.db.log_query(f"SELECT * FROM products WHERE name LIKE '%{term}%'", random.uniform(5, 50))
        
        self.app.log("INFO", trace_id, f"Found {random.randint(0, 50)} results", user_id=user)
        self.lb.log_request(ip, "GET", f"/api/v1/products?q={term}", 200, 5000, ua, 100)

    def flow_sqli(self):
        """Simulates an SQL Injection attempt"""
        trace_id = get_trace_id()
        ip = get_random_ip() # Or attacker IP
        ua = "Mozilla/5.0 (Kali; Linux x86_64)" # Suspicious UA
        payload = "' OR 1=1 --"
        
        self.lb.log_request(ip, "GET", f"/api/v1/products?q={payload}", 200, 0, ua, 15)
        self.app.log("INFO", trace_id, f"Search request: '{payload}'", user_id=None)
        
        # DB log shows the injection
        self.db.log_query(f"SELECT * FROM products WHERE name LIKE '%{payload}%'", 120, status="ERROR", error="Syntax error near '--'")
        
        self.app.log("ERROR", trace_id, "SQL Exception caught", extra={"query_fragment": payload})
        self.lb.log_request(ip, "GET", f"/api/v1/products?q={payload}", 500, 120, ua, 150)

    def flow_error_500(self):
        trace_id = get_trace_id()
        ip = get_random_ip()
        ua = get_random_ua()
        
        self.lb.log_request(ip, "GET", "/api/v1/dashboard", 500, 0, ua, 20)
        self.app.log("INFO", trace_id, "Fetch dashboard data")
        self.db.log_query("SELECT sum(amount) FROM orders", 2000, status="ERROR", error="Connection refused")
        self.app.log("ERROR", trace_id, "Database connection failed", extra={"error": "OperationalError"})
        self.lb.log_request(ip, "GET", "/api/v1/dashboard", 500, 50, ua, 2100) # Long duration

    # --- ATTACK PATTERNS ---
    
    def attack_brute_force(self):
        target_ip = "10.66.77.88" # Fixed attacker IP
        target_user = "admin"
        
        # Burst of 5-8 failed logins from SAME IP
        for _ in range(random.randint(5, 8)):
            self.flow_login(success=False, override_ip=target_ip, override_user=target_user)
