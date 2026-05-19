import sys
sys.path.append(r"c:\Users\ASUS\OneDrive\Bureau\Looyas\ITSM_Agent\agent")

from agentt.mcp_server.server import neo4j_driver

HISTORICAL_ID = "INC-2026-88D58E03"
CHILD_ID      = "INC-2026-47A5D6E1"
CHILD_LINEAR  = "58a327b3-3f36-4b96-8f17-69b4ab5ab20d"

print("=== Diagnosing duplicate node ===\n")

with neo4j_driver.session() as session:

    # 1. Check what nodes exist
    r = session.run("MATCH (t:ResolvedTicket) RETURN t.incident_id, t.linear_issue_ids")
    print("All ResolvedTicket nodes:")
    for rec in r:
        print(f"  incident_id={rec['t.incident_id']}  linear_issue_ids={rec['t.linear_issue_ids']}")

    # 2. Verify the existence check that the code does
    r2 = session.run(
        "MATCH (t:ResolvedTicket {incident_id: $hist_id}) RETURN count(t) AS cnt",
        {"hist_id": HISTORICAL_ID}
    )
    rec2 = r2.single()
    print(f"\nExistence check for '{HISTORICAL_ID}': cnt = {rec2['cnt'] if rec2 else 'NO RECORD'}")

    # 3. Fix: append CHILD's linear_issue_id to HISTORICAL node and delete child node
    print("\n=== Applying manual fix ===\n")

    # Append child linear ID to historical node's list
    session.run("""
        MATCH (t:ResolvedTicket {incident_id: $hist_id})
        SET t.linear_issue_ids = CASE
          WHEN $child_linear IN coalesce(t.linear_issue_ids, []) THEN t.linear_issue_ids
          ELSE coalesce(t.linear_issue_ids, []) + $child_linear
        END,
        t.linear_issue_id = $child_linear
    """, {"hist_id": HISTORICAL_ID, "child_linear": CHILD_LINEAR})
    print(f"[OK] Appended '{CHILD_LINEAR}' to '{HISTORICAL_ID}'.linear_issue_ids")

    # Move all HAS_MEMORY edges from child to historical node (if any extra were created)
    session.run("""
        MATCH (n)-[:HAS_MEMORY]->(child:ResolvedTicket {incident_id: $child_id})
        MATCH (hist:ResolvedTicket {incident_id: $hist_id})
        MERGE (n)-[:HAS_MEMORY]->(hist)
    """, {"child_id": CHILD_ID, "hist_id": HISTORICAL_ID})
    print(f"[OK] Migrated any HAS_MEMORY edges from '{CHILD_ID}' to '{HISTORICAL_ID}'.")

    # Delete the duplicate child node
    session.run("""
        MATCH (t:ResolvedTicket {incident_id: $child_id})
        DETACH DELETE t
    """, {"child_id": CHILD_ID})
    print(f"[OK] Deleted duplicate node '{CHILD_ID}'.")

    # 4. Verify final state
    print("\n=== Final state ===")
    r3 = session.run("""
        MATCH (t:ResolvedTicket {incident_id: $hist_id})
        RETURN t.incident_id, t.linear_issue_id, t.linear_issue_ids
    """, {"hist_id": HISTORICAL_ID})
    rec3 = r3.single()
    if rec3:
        print(f"  incident_id:      {rec3['t.incident_id']}")
        print(f"  linear_issue_id:  {rec3['t.linear_issue_id']}")
        print(f"  linear_issue_ids: {rec3['t.linear_issue_ids']}")
    else:
        print("[FAIL] Node not found!")

print("\n[COMPLETE] Fix applied.")
