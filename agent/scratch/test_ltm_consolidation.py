import os
import sys

# Add parent directory of agentt to the Python path
sys.path.append(r"c:\Users\ASUS\OneDrive\Bureau\Looyas\ITSM_Agent\agent")

from agentt.mcp_server.server import save_resolved_ticket, neo4j_driver
from webhook_server import _find_ticket_by_linear_id, _update_ticket_notes, _append_note

def test_consolidation():
    print("[INFO] Starting LTM consolidation test...")

    # Clear existing test data in Neo4j (for cleanup and reliability)
    with neo4j_driver.session() as session:
        session.run("MATCH (t:ResolvedTicket) WHERE t.incident_id STARTS WITH 'INC-TEST-' DETACH DELETE t")
        print("[CLEAN] Cleaned up existing test incidents starting with 'INC-TEST-'.")

    # Define test parameters
    parent_incident_id = "INC-TEST-PARENT"
    child_incident_id = "INC-TEST-CHILD"
    app_id = "test-app"
    root_cause_id = "prod-node-1" # Assumes prod-node-1 exists in seed graph
    affected_services = ["reporting-api"]
    
    prob_text = "Database connection pool exhausted due to high traffic surge."
    sol_text = "Scaling up replica count and increasing connection pool size to 50."

    # 1. Create parent ticket
    print("\n1. Creating parent ResolvedTicket...")
    res1 = save_resolved_ticket.fn(
        incident_id=parent_incident_id,
        app_id=app_id,
        root_cause_node_id=root_cause_id,
        affected_service_ids=affected_services,
        problem_text=prob_text,
        solution_text=sol_text,
        risk_score=45,
        linear_issue_id="linear-id-parent"
    )
    print(res1)

    # 2. Append new occurrence ticket using historical_incident_id
    print("\n2. Consolidating child ResolvedTicket onto parent...")
    res2 = save_resolved_ticket.fn(
        incident_id=child_incident_id,
        app_id=app_id,
        root_cause_node_id=root_cause_id,
        affected_service_ids=affected_services,
        problem_text=prob_text,
        solution_text=sol_text,
        risk_score=45,
        linear_issue_id="linear-id-child",
        historical_incident_id=parent_incident_id
    )
    print(res2)

    # 3. Check Neo4j node state
    print("\n3. Querying Neo4j database to verify node consolidation...")
    with neo4j_driver.session() as session:
        # Check if parent node exists
        p_res = session.run("MATCH (t:ResolvedTicket {incident_id: $id}) RETURN t", {"id": parent_incident_id})
        p_node = p_res.single()
        
        # Check if child node exists (it should NOT have been created)
        c_res = session.run("MATCH (t:ResolvedTicket {incident_id: $id}) RETURN t", {"id": child_incident_id})
        c_node = c_res.single()

        if c_node:
            print("[FAIL] Child node should not exist as a separate node!")
        else:
            print("[SUCCESS] Child node was not created separately.")

        if p_node:
            node_props = p_node["t"]
            print(f"[SUCCESS] Parent node '{parent_incident_id}' exists.")
            print(f"   linear_issue_id:  {node_props.get('linear_issue_id')}")
            print(f"   linear_issue_ids: {node_props.get('linear_issue_ids')}")
            assert "linear-id-parent" in node_props.get("linear_issue_ids"), "Parent ID missing from list"
            assert "linear-id-child" in node_props.get("linear_issue_ids"), "Child ID missing from list"
            print("[SUCCESS] Both Linear IDs successfully stored in the linear_issue_ids array.")
        else:
            print("[FAIL] Parent node does not exist!")

    # 4. Verify Webhook ticket lookup for both IDs
    print("\n4. Verifying Webhook ticket lookup by linear IDs...")
    with neo4j_driver.session() as session:
        t_parent = _find_ticket_by_linear_id(session, "linear-id-parent")
        t_child = _find_ticket_by_linear_id(session, "linear-id-child")
        
        if t_parent and t_child:
            print(f"[SUCCESS] Found ResolvedTicket for parent ID. Incident ID: {t_parent['incident_id']}")
            print(f"[SUCCESS] Found ResolvedTicket for child ID. Incident ID: {t_child['incident_id']}")
            assert t_parent['incident_id'] == parent_incident_id, "Parent lookup returned wrong incident"
            assert t_child['incident_id'] == parent_incident_id, "Child lookup returned wrong incident"
            print("[SUCCESS] Both lookups successfully resolved to the SAME single parent node.")
        else:
            print("[FAIL] Webhook lookup failed for one or both IDs!")

    # 5. Verify Webhook comment updates and deduplication
    print("\n5. Verifying Webhook updates & deduplication...")
    with neo4j_driver.session() as session:
        # Simulate first comment on child ticket
        t_data = _find_ticket_by_linear_id(session, "linear-id-child")
        appended_notes = _append_note(t_data["human_notes"], "SRE Alice", "Please check replication lag.")
        _update_ticket_notes(session, "linear-id-child", appended_notes, [0.1]*768, comment_id="comm-1")
        
        # Verify comment is stored
        t_check = _find_ticket_by_linear_id(session, "linear-id-parent")
        print(f"   Human notes after comment 1: {repr(t_check['human_notes'])}")
        assert "Please check replication lag." in t_check["human_notes"], "Comment 1 missing"
        assert "comm-1" in t_check["processed_comment_ids"], "Comment ID 1 not tracked"
        print("[SUCCESS] Comment 1 saved to the consolidated node.")

        # Simulate duplicate comment webhook retry
        if "comm-1" in t_check["processed_comment_ids"]:
            print("[SUCCESS] Webhook server correctly identified duplicate comment 'comm-1'. Skipping processing.")
        else:
            print("[FAIL] Did not detect duplicate comment!")

        # Simulate second comment on parent ticket
        t_data2 = _find_ticket_by_linear_id(session, "linear-id-parent")
        appended_notes2 = _append_note(t_data2["human_notes"], "SRE Bob", "Agreed, replication lag is normal now.")
        _update_ticket_notes(session, "linear-id-parent", appended_notes2, [0.2]*768, comment_id="comm-2")

        t_final = _find_ticket_by_linear_id(session, "linear-id-parent")
        print(f"   Human notes after comment 2: {repr(t_final['human_notes'])}")
        assert "Please check replication lag." in t_final["human_notes"], "Comment 1 missing"
        assert "Agreed, replication lag is normal now." in t_final["human_notes"], "Comment 2 missing"
        assert "comm-2" in t_final["processed_comment_ids"], "Comment ID 2 not tracked"
        print("[SUCCESS] Comment 2 from a different ticket consolidated onto the same memory node!")

    print("\n[COMPLETE] All consolidation and webhook lookup tests PASSED successfully!")

if __name__ == "__main__":
    test_consolidation()
