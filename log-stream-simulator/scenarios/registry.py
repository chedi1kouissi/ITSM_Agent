import random

def nominal_traffic(engine):
    """Mostly happy paths, occasional 500 error."""
    r = random.random()
    if r < 0.1:
        engine.flow_login(success=False) # Normal typo
    elif r < 0.3:
        engine.flow_login(success=True)
    elif r < 0.8:
        engine.flow_search_product()
    elif r < 0.82:
        engine.flow_error_500()
    else:
        # Idle / Browse homepage (Log only LB)
        pass

def brute_force_scenario(engine):
    """Heavier traffic with Brute Force spikes."""
    # Run nominal background traffic
    if random.random() < 0.7:
        nominal_traffic(engine)
    
    # Inject Brute Force every now and then
    if random.random() < 0.2:
        engine.attack_brute_force()

def sqli_scenario(engine):
    """Nominal traffic mixed with SQL Injection attempts."""
    if random.random() < 0.8:
        nominal_traffic(engine)
    
    if random.random() < 0.1:
        engine.flow_sqli()

def chaos_scenario(engine):
    """Everything everywhere all at once"""
    scenarios = [nominal_traffic, brute_force_scenario, sqli_scenario]
    random.choice(scenarios)(engine)

SCENARIOS = {
    "nominal": nominal_traffic,
    "brute_force": brute_force_scenario,
    "sqli": sqli_scenario,
    "chaos": chaos_scenario
}
