"""P1: the runtime integration.

Every public method of the contract is executed against a live network with
real consensus, the state is read back and the retryable failure path is
exercised. This is what establishes that the storage types, the non
deterministic blocks, the exception propagation and the method signatures work
in the GenLayer runtime and not only in the direct harness.
"""

from tests.integration.helpers import (
    call_result,
    failure_message,
    open_case,
    read,
    ready_case,
    record_order,
    register_policy,
    votes,
    write,
)

CLAUSE = {
    "clause_id": "C1",
    "text": "Item must be unused or in like-new condition.",
    "kind": "INTERPRETIVE",
    "topic": "CONDITION",
}


def test_every_public_method_runs_on_the_runtime(client, contract, accounts):
    merchant = accounts["merchant"]
    buyer = accounts["buyer"]
    outsider = accounts["outsider"]

    # --- configuration (owner) -------------------------------------------
    # The challenge window is set to one second, so the case can be finalized
    # inside the test without waiting for days.
    write(client, contract, "set_config", merchant, [259200, 1, 2, 8])
    write(client, contract, "set_escalation_role", merchant, [outsider.address])
    config = read(client, contract, "get_config", merchant)
    assert config["max_challenge_rounds"] == 2
    assert config["escalation_role"] == outsider.address.lower()

    # --- policies ---------------------------------------------------------
    policy_id = register_policy(
        client,
        contract,
        merchant,
        title="Runtime policy",
        required=["TEXT_STATEMENT"],
        excluded=["PERISHABLE"],
        max_fee=1500,
        clauses=[CLAUSE],
    )
    policy = read(client, contract, "get_policy", merchant, [policy_id])
    assert policy["merchant"] == merchant.address.lower()
    assert policy["status"] == "ACTIVE"
    assert policy["clauses"][0]["rule"] == ""

    version = call_result(
        write(
            client,
            contract,
            "update_policy",
            merchant,
            [
                policy_id,
                "Runtime policy v2",
                518400,
                [],
                ["TEXT_STATEMENT"],
                2000,
                [CLAUSE],
            ],
        )
    )
    assert version == 2
    pinned = read(client, contract, "get_policy_version", merchant, [policy_id, 1])
    assert pinned["version"] == 1

    active = read(client, contract, "list_active_policies", merchant, [merchant.address])
    assert policy_id in active

    # --- orders -----------------------------------------------------------
    order_id = record_order(client, contract, merchant, buyer.address, policy_id)
    order = read(client, contract, "get_order", buyer, [order_id])
    assert order["policy_version"] == 1
    assert order["buyer"] == buyer.address.lower()

    # --- case, evidence, assessment --------------------------------------
    case_id = open_case(client, contract, buyer, order_id)
    case = read(client, contract, "get_case", buyer, [case_id])
    assert case["status"] == "OPEN"
    assert case["contested_fields"] == []

    write(
        client,
        contract,
        "submit_evidence",
        buyer,
        [case_id, "TEXT_STATEMENT", "The unit arrived defective."],
    )
    evidence = read(client, contract, "get_evidence", buyer, [case_id])
    assert len(evidence) == 1
    assert evidence[0]["side"] == "BUYER"

    write(client, contract, "request_seller_response", outsider, [case_id])
    write(
        client,
        contract,
        "submit_evidence",
        merchant,
        [case_id, "TEXT_STATEMENT", "The unit worked when it left."],
    )
    write(client, contract, "close_response_window", merchant, [case_id])
    assert read(client, contract, "get_case_status", buyer, [case_id]) == "READY"

    receipt = write(client, contract, "evaluate_case", outsider, [case_id])
    assert receipt["status_name"] == "FINALIZED"
    assert votes(receipt) == {"agree"}

    history = read(client, contract, "get_assessment_history", buyer, [case_id])
    assert len(history) == 1
    assert history[0]["verdict"] == "ELIGIBLE_FULL"
    assert history[0]["produced_by"] == "EVALUATION"
    assert history[0]["net_refund_bps"] == 10000
    assert "RETURN_WINDOW:PASS" in history[0]["deterministic_results"]
    assert "REQUIRED_EVIDENCE_AVAILABLE:PASS" in history[0]["deterministic_results"]

    # --- challenge and re-evaluation -------------------------------------
    write(
        client,
        contract,
        "challenge_assessment",
        buyer,
        [case_id, "The buyer adds a photograph of the boxed and unused unit."],
    )
    assert read(client, contract, "get_case_status", buyer, [case_id]) == "CHALLENGED"
    write(
        client,
        contract,
        "submit_evidence",
        buyer,
        [case_id, "TEXT_STATEMENT", "A new photograph of the boxed unit."],
    )
    receipt = write(client, contract, "re_evaluate", outsider, [case_id])
    assert receipt["status_name"] == "FINALIZED"
    history = read(client, contract, "get_assessment_history", buyer, [case_id])
    assert len(history) == 2
    assert history[1]["produced_by"] == "RE_EVALUATION"

    # --- finality ---------------------------------------------------------
    # The simulator uses its own block clock, so the challenge window cannot
    # elapse inside a test. The refusal is therefore what is checked here; the
    # successful finalization is covered by the direct tests.
    receipt = write(client, contract, "finalize_case", outsider, [case_id])
    leader = receipt["consensus_data"]["leader_receipt"][0]
    assert leader["execution_result"] == "ERROR"
    assert "EXPECTED: challenge window is still open" in failure_message(receipt)
    assert read(client, contract, "get_case_status", buyer, [case_id]) == "RE_EVALUATED"

    # --- deprecation ------------------------------------------------------
    write(client, contract, "deprecate_policy", merchant, [policy_id])
    assert read(client, contract, "get_policy", merchant, [policy_id])["status"] == (
        "DEPRECATED"
    )


def test_a_second_case_can_be_escalated_on_the_runtime(client, contract, accounts):
    merchant = accounts["merchant"]
    buyer = accounts["buyer"]
    outsider = accounts["outsider"]

    policy_id = register_policy(client, contract, merchant, title="Escalation policy")
    order_id = record_order(client, contract, merchant, buyer.address, policy_id)
    case_id = open_case(client, contract, buyer, order_id)
    ready_case(client, contract, merchant, buyer, case_id)

    receipt = write(client, contract, "evaluate_case", outsider, [case_id])
    assert receipt["status_name"] == "FINALIZED"

    write(client, contract, "escalate_case", outsider, [case_id, "needs a human"])
    case = read(client, contract, "get_case", buyer, [case_id])
    assert case["status"] == "ESCALATED"
    assert case["escalation_reason"] == "needs a human"


def test_a_case_can_be_withdrawn_on_the_runtime(client, contract, accounts):
    merchant = accounts["merchant"]
    buyer = accounts["buyer"]

    policy_id = register_policy(client, contract, merchant, title="Withdraw policy")
    order_id = record_order(client, contract, merchant, buyer.address, policy_id)
    case_id = open_case(client, contract, buyer, order_id)

    write(client, contract, "withdraw_case", buyer, [case_id])
    assert read(client, contract, "get_case_status", buyer, [case_id]) == "WITHDRAWN"


def test_a_retryable_failure_is_reported_as_an_error(client, contract, accounts):
    """A rejected call fails the transaction, it does not produce a verdict."""
    merchant = accounts["merchant"]
    buyer = accounts["buyer"]

    policy_id = register_policy(client, contract, merchant, title="Failure policy")
    order_id = record_order(client, contract, merchant, buyer.address, policy_id)
    case_id = open_case(client, contract, buyer, order_id)

    # The assessment before the response window is closed is refused.
    receipt = write(client, contract, "evaluate_case", accounts["outsider"], [case_id])
    leader = receipt["consensus_data"]["leader_receipt"][0]
    assert leader["execution_result"] == "ERROR"
    assert (
        "EXPECTED: seller response window is not closed yet"
        in failure_message(receipt)
    )
    assert read(client, contract, "get_assessment_history", buyer, [case_id]) == []
    assert read(client, contract, "get_case_status", buyer, [case_id]) == "OPEN"
