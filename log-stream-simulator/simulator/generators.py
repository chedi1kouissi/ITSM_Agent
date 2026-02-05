import random
import uuid

IPS = [
    "192.168.1.10", "10.0.0.5", "172.16.0.23", "203.0.113.45", "198.51.100.12",
    "45.33.22.11", "66.249.66.1", "104.21.55.2", "8.8.8.8", "1.1.1.1"
]

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Mobile/15E148 Safari/604.1"
]

USERS = [f"user_{i}" for i in range(1, 100)] + [None]*20 # 20% anonymous

def get_random_ip():
    return random.choice(IPS)

def get_random_ua():
    return random.choice(USER_AGENTS)

def get_random_user():
    return random.choice(USERS)

def get_trace_id():
    return str(uuid.uuid4())[:8]
