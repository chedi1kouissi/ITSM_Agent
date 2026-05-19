import sys
sys.path.append(r"c:\Users\ASUS\OneDrive\Bureau\Looyas\ITSM_Agent\agent")

# Import the graph wrapper (the exact function the LLM calls)
from agentt.graph import _save_resolved_ticket
from agentt.mcp_server.server import neo4j_driver

HISTORICAL_ID = "INC-2026-88D58E03"
TEST_CHILD_ID = "INC-TEST-WRAPPER-CHILD"
TEST_LINEAR_ID = "linear-wrapper-test-id"

print("=== Testing graph.py wrapper fix ===\n")

# Verify the historical node exists in Neo4j
with neo4j_driver.session() as session:
    r = session.run(
        "MATCH (t:ResolvedTicket {incident_id: $id}) RETURN t.linear_issue_ids",
        {"id": HISTORICAL_ID}
    )
    rec = r.single()
    if rec:
        print(f"[OK] Historical node '{HISTORICAL_ID}' found.")
        print(f"     linear_issue_ids before: {rec['t.linear_issue_ids']}")
    else:
        print(f"[FAIL] Historical node not found!")
        sys.exit(1)

# Call the wrapper with historical_incident_id (exactly as the LLM would)
print(f"\nCalling _save_resolved_ticket with historical_incident_id='{HISTORICAL_ID}'...")
result = _save_resolved_ticket(
    incident_id=TEST_CHILD_ID,
    app_id="ecommerce-prod",
    root_cause_node_id="payment-db",
    affected_service_ids=["payment-api", "payment-db"],
    problem_text="Payment DB connection pool exhaustion and slow queries.",
    solution_text="Restart pods, scale connection pool.",
    risk_score=45,
    linear_issue_id=TEST_LINEAR_ID,
    human_notes="",
    historical_incident_id=HISTORICAL_ID
)
print(f"Result: {result}")

# Verify final state
with neo4j_driver.session() as session:
    # Child node should NOT exist
    cr = session.run("MATCH (t:ResolvedTicket {incident_id: $id}) RETURN count(t) AS cnt", {"id": TEST_CHILD_ID})
    child_cnt = cr.single()["cnt"]
    if child_cnt == 0:
        print(f"\n[SUCCESS] No duplicate child node created for '{TEST_CHILD_ID}'.")
    else:
        print(f"\n[FAIL] Duplicate child node was created!")

    # Historical node should now have both IDs
    hr = session.run(
        "MATCH (t:ResolvedTicket {incident_id: $id}) RETURN t.linear_issue_ids",
        {"id": HISTORICAL_ID}
    )
    hrec = hr.single()
    if hrec:
        ids = hrec["t.linear_issue_ids"]
        print(f"[INFO] Historical node linear_issue_ids after: {ids}")
        if TEST_LINEAR_ID in ids:
            print(f"[SUCCESS] Wrapper correctly passed historical_incident_id through - IDs consolidated!")
        else:
            print(f"[FAIL] New linear ID not found in historical node!")

    # Cleanup
    session.run("MATCH (t:ResolvedTicket {incident_id: $id}) DETACH DELETE t", {"id": TEST_CHILD_ID})
    session.run("""
        MATCH (t:ResolvedTicket {incident_id: $id})
        SET t.linear_issue_ids = [x IN t.linear_issue_ids WHERE x <> $test_id],
            t.linear_issue_id  = LAST([x IN t.linear_issue_ids WHERE x <> $test_id])
    """, {"id": HISTORICAL_ID, "test_id": TEST_LINEAR_ID})
    print("\n[CLEAN] Test cleanup done.")
