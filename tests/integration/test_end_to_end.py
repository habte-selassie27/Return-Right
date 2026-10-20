"""End to end flow against a live network: deploy, dispute, assessment, challenge."""

import pytest

from tests.integration.helpers import (
    NOT_ELIGIBLE_CLAIM,
    call_result,
    days_ago,
    failure_message,
    open_case,
    read,
    ready_case,
    record_order,
    register_policy,
    votes,
    write,
)


def test_deploy_succeeds_and_the_config_is_readable(client, contract, accounts):
    config = read(client, contract, "get_config", accounts["merchant"])
    assert config["seller_response_window_seconds"] == 259200
    assert config["challenge_window_seconds"] == 172800
    assert config["max_challenge_rounds"] == 2
    assert config["max_evidence_per_side"] == 8


def test_full_dispute_flow(client, contract, accounts):
    merchant = accounts["merchant"]
    buyer = accounts["buyer"]

    policy_id = register_policy(client, contract, merchant)
    assert policy_id == "POL-0"

    order_id = record_order(
        client, contract, merchant, buyer.address, policy_id
    )
    assert order_id == "ORD-0"

    case_id = open_case(client, contract, buyer, order_id)
    assert case_id == "CAS-0"

    # Both sides submit their evidence.
    write(
        client,
        contract,
        "submit_evidence",
        buyer,
        [case_id, "TEXT_STATEMENT", "The unit arrived defective and does not power on."],
    )
    write(client, contract, "request_seller_response", buyer, [case_id])
    write(
        client,
        contract,
        "submit_evidence",
        merchant,
        [case_id, "TEXT_STATEMENT", "The unit worked when it left our warehouse."],
    )
    write(client, contract, "close_response_window", merchant, [case_id])

    assert read(client, contract, "get_case_status", buyer, [case_id]) == "READY"

    receipt = write(client, contract, "evaluate_case", accounts["outsider"], [case_id])
    assert receipt["status_name"] == "FINALIZED"
    # Every validator agreed with the leader.
    assert votes(receipt) == {"agree"}

    history = read(client, contract, "get_assessment_history", buyer, [case_id])
    assert len(history) == 1
    assessment = history[0]
    assert assessment["verdict"] == "ELIGIBLE_FULL"
    assert assessment["produced_by"] == "EVALUATION"
    assert assessment["fee_bps"] == 0
    assert "RETURN_WINDOW:PASS" in assessment["deterministic_results"]
    assert "EXCLUDED_CATEGORY:PASS" in assessment["deterministic_results"]
    # The model stand-in cites the evidence it was given.
    assert assessment["cited_evidence_ids"] == ["EV-0", "EV-1"]
    assert assessment["cited_clause_ids"] == ["C1"]


def test_a_not_eligible_case_is_recorded(client, contract, accounts):
    merchant = accounts["merchant"]
    buyer = accounts["buyer"]

    policy_id = register_policy(client, contract, merchant, title="Second policy")
    order_id = record_order(client, contract, merchant, buyer.address, policy_id)
    case_id = open_case(
        client, contract, buyer, order_id, reason="NOT_AS_DESCRIBED",
        claim=NOT_ELIGIBLE_CLAIM,
    )
    ready_case(client, contract, merchant, buyer, case_id)

    receipt = write(client, contract, "evaluate_case", accounts["outsider"], [case_id])
    assert receipt["status_name"] == "FINALIZED"
    assert votes(receipt) == {"agree"}

    history = read(client, contract, "get_assessment_history", buyer, [case_id])
    assert history[0]["verdict"] == "NOT_ELIGIBLE"


def test_a_hard_failure_never_reaches_the_model(client, contract, accounts):
    merchant = accounts["merchant"]
    buyer = accounts["buyer"]

    policy_id = register_policy(
        client,
        contract,
        merchant,
        title="No perishables",
        excluded=["PERISHABLE"],
    )
    order_id = record_order(
        client,
        contract,
        merchant,
        buyer.address,
        policy_id,
        category="PERISHABLE",
    )
    case_id = open_case(client, contract, buyer, order_id)
    ready_case(client, contract, merchant, buyer, case_id)

    receipt = write(client, contract, "evaluate_case", accounts["outsider"], [case_id])
    assert receipt["status_name"] == "FINALIZED"

    history = read(client, contract, "get_assessment_history", buyer, [case_id])
    assessment = history[0]
    assert assessment["verdict"] == "NOT_ELIGIBLE"
    assert "HARD_FAIL" in assessment["flags"]
    # The reasoning digest of the deterministic path proves the model was not used.
    assert assessment["reasoning_digest"] == "deterministic hard check failed"


def test_challenge_and_re_evaluation_append_to_the_history(client, contract, accounts):
    merchant = accounts["merchant"]
    buyer = accounts["buyer"]

    policy_id = register_policy(client, contract, merchant, title="Third policy")
    order_id = record_order(client, contract, merchant, buyer.address, policy_id)
    case_id = open_case(client, contract, buyer, order_id)
    ready_case(client, contract, merchant, buyer, case_id)

    receipt = write(client, contract, "evaluate_case", accounts["outsider"], [case_id])
    assert receipt["status_name"] == "FINALIZED"

    write(
        client,
        contract,
        "challenge_assessment",
        buyer,
        [case_id, "The buyer adds a photograph of the boxed and unused unit."],
    )
    assert read(client, contract, "get_case_status", buyer, [case_id]) == "CHALLENGED"

    receipt = write(client, contract, "re_evaluate", accounts["outsider"], [case_id])
    assert receipt["status_name"] == "FINALIZED"

    history = read(client, contract, "get_assessment_history", buyer, [case_id])
    assert len(history) == 2
    assert history[0]["produced_by"] == "EVALUATION"
    assert history[1]["produced_by"] == "RE_EVALUATION"
    assert history[0]["assessment_id"] != history[1]["assessment_id"]


def test_the_permutation_of_the_evidence_does_not_change_the_verdict(
    client, contract, accounts
):
    merchant = accounts["merchant"]
    buyer = accounts["buyer"]

    policy_id = register_policy(client, contract, merchant, title="Fourth policy")

    # Case one: the buyer speaks first.
    order_one = record_order(client, contract, merchant, buyer.address, policy_id)
    case_one = open_case(client, contract, buyer, order_one)
    write(
        client,
        contract,
        "submit_evidence",
        buyer,
        [case_one, "TEXT_STATEMENT", "alpha statement"],
    )
    write(client, contract, "request_seller_response", buyer, [case_one])
    write(
        client,
        contract,
        "submit_evidence",
        merchant,
        [case_one, "TEXT_STATEMENT", "beta statement"],
    )
    write(client, contract, "close_response_window", merchant, [case_one])
    write(client, contract, "evaluate_case", accounts["outsider"], [case_one])

    # Case two: the same two statements, submitted in the opposite order.
    order_two = record_order(client, contract, merchant, buyer.address, policy_id)
    case_two = open_case(client, contract, buyer, order_two)
    write(client, contract, "request_seller_response", buyer, [case_two])
    write(
        client,
        contract,
        "submit_evidence",
        merchant,
        [case_two, "TEXT_STATEMENT", "beta statement"],
    )
    write(
        client,
        contract,
        "submit_evidence",
        buyer,
        [case_two, "TEXT_STATEMENT", "alpha statement"],
    )
    write(client, contract, "close_response_window", merchant, [case_two])
    write(client, contract, "evaluate_case", accounts["outsider"], [case_two])

    history_one = read(client, contract, "get_assessment_history", buyer, [case_one])
    history_two = read(client, contract, "get_assessment_history", buyer, [case_two])
    assert history_one[0]["verdict"] == history_two[0]["verdict"]


def test_a_rejected_write_reports_the_documented_error_prefix(client, contract, accounts):
    merchant = accounts["merchant"]
    buyer = accounts["buyer"]

    policy_id = register_policy(client, contract, merchant, title="Fifth policy")
    order_id = record_order(client, contract, merchant, buyer.address, policy_id)

    # The merchant may not open a case on the buyer's order.
    receipt = write(
        client,
        contract,
        "open_case",
        merchant,
        [order_id, "DEFECTIVE", "The unit arrived defective."],
    )
    message = failure_message(receipt)
    assert "EXPECTED: caller is not the order buyer" in message


def test_a_case_cannot_be_assessed_before_the_response_window_is_closed(
    client, contract, accounts
):
    """Nobody may be judged before the other side had the chance to answer."""
    merchant = accounts["merchant"]
    buyer = accounts["buyer"]

    policy_id = register_policy(client, contract, merchant, title="Sixth policy")
    order_id = record_order(client, contract, merchant, buyer.address, policy_id)
    case_id = open_case(client, contract, buyer, order_id)

    receipt = write(client, contract, "evaluate_case", accounts["outsider"], [case_id])
    leader = receipt["consensus_data"]["leader_receipt"][0]
    assert leader["execution_result"] == "ERROR"
    assert (
        "EXPECTED: seller response window is not closed yet"
        in failure_message(receipt)
    )

    # Nothing was written.
    assert read(client, contract, "get_case_status", buyer, [case_id]) == "OPEN"
    assert read(client, contract, "get_assessment_history", buyer, [case_id]) == []


def test_a_contested_delivery_date_is_decided_by_the_validators(client, contract, accounts):
    """A contested merchant record is never a silent hard failure."""
    merchant = accounts["merchant"]
    buyer = accounts["buyer"]

    policy_id = register_policy(client, contract, merchant, title="Seventh policy")
    # The delivery date is far outside the return window.
    order_id = record_order(
        client,
        contract,
        merchant,
        buyer.address,
        policy_id,
        delivered_at=days_ago(30),
    )
    case_id = open_case(client, contract, buyer, order_id)

    write(client, contract, "contest_order_record", buyer, [case_id, ["DELIVERY_DATE"]])
    assert read(client, contract, "get_case", buyer, [case_id])["contested_fields"] == [
        "DELIVERY_DATE"
    ]

    ready_case(client, contract, merchant, buyer, case_id)
    receipt = write(client, contract, "evaluate_case", accounts["outsider"], [case_id])
    assert receipt["status_name"] == "FINALIZED"

    assessment = read(client, contract, "get_assessment_history", buyer, [case_id])[0]
    assert "RETURN_WINDOW:CONTESTED" in assessment["deterministic_results"]
    assert "HARD_FAIL" not in assessment["flags"]
    assert "ORDER_RECORD_CONTESTED" in assessment["flags"]
    assert assessment["verdict"] == "ELIGIBLE_FULL"


def test_a_deterministic_clause_without_an_enforced_rule_is_rejected(
    client, contract, accounts
):
    """A clause may only be deterministic when the code really enforces it."""
    merchant = accounts["merchant"]

    receipt = write(
        client,
        contract,
        "register_policy",
        merchant,
        [
            "Unenforceable policy",
            259200,
            [],
            [],
            0,
            [
                {
                    "clause_id": "C1",
                    "text": "The item must be blue.",
                    "kind": "DETERMINISTIC",
                    "topic": "OTHER",
                }
            ],
        ],
    )
    leader = receipt["consensus_data"]["leader_receipt"][0]
    assert leader["execution_result"] == "ERROR"
    assert "EXPECTED: unsupported deterministic clause" in failure_message(receipt)
