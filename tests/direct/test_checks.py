"""Deterministic checks: the code decides everything code can decide."""

from tests.conftest import DETERMINISTIC_CLAUSE, LLM_PROMPT_PATTERN, llm_reply

INTERPRETIVE_CLAUSE = {
    "clause_id": "C1",
    "text": "Item must be unused or in like-new condition.",
    "kind": "INTERPRETIVE",
    "topic": "CONDITION",
}


def test_return_window_passes_at_the_boundary(deployed):
    dep = deployed
    policy_id = dep.register_policy(
        window=259200, required=[], clauses=[DETERMINISTIC_CLAUSE]
    )
    order_id = dep.record_order(policy_id, delivered_at="2026-01-01T00:00:00Z")

    # Exactly at the boundary the request is still inside the window.
    dep.warp("2026-01-04T00:00:00Z")
    case_id = dep.open_case(order_id)
    dep.ready_case(case_id)

    with dep.as_stranger():
        dep.contract.evaluate_case(case_id)

    assessment = dep.contract.get_assessment_history(case_id)[0]
    assert "RETURN_WINDOW:PASS" in assessment["deterministic_results"]
    assert assessment["verdict"] == "ELIGIBLE_FULL"


def test_return_window_fails_one_second_late(deployed):
    dep = deployed
    policy_id = dep.register_policy(window=259200, clauses=[DETERMINISTIC_CLAUSE])
    order_id = dep.record_order(policy_id, delivered_at="2026-01-01T00:00:00Z")

    dep.warp("2026-01-04T00:00:01Z")
    case_id = dep.open_case(order_id)
    dep.ready_case(case_id)

    dep.mock_llm(LLM_PROMPT_PATTERN, llm_reply(verdict="ELIGIBLE_FULL"))
    with dep.as_stranger():
        dep.contract.evaluate_case(case_id)

    assessment = dep.contract.get_assessment_history(case_id)[0]
    assert "RETURN_WINDOW:FAIL" in assessment["deterministic_results"]
    assert assessment["verdict"] == "NOT_ELIGIBLE"
    assert "HARD_FAIL" in assessment["flags"]
    # The model was never asked: a hard check cannot be overturned.
    assert dep.llm_hits() == 0


def test_excluded_category_forces_not_eligible_and_skips_the_model(deployed):
    dep = deployed
    policy_id = dep.register_policy(
        excluded=["PERISHABLE"], clauses=[INTERPRETIVE_CLAUSE]
    )
    order_id = dep.record_order(policy_id, category="PERISHABLE")
    case_id = dep.open_case(order_id)
    dep.ready_case(case_id)

    dep.mock_llm(LLM_PROMPT_PATTERN, llm_reply(verdict="ELIGIBLE_FULL"))
    with dep.as_stranger():
        dep.contract.evaluate_case(case_id)

    assessment = dep.contract.get_assessment_history(case_id)[0]
    assert "EXCLUDED_CATEGORY:FAIL" in assessment["deterministic_results"]
    assert assessment["verdict"] == "NOT_ELIGIBLE"
    assert assessment["confidence_band"] == "HIGH"
    assert "HARD_FAIL" in assessment["flags"]
    assert dep.llm_hits() == 0


def test_fully_deterministic_policy_never_calls_the_model(deployed):
    dep = deployed
    policy_id = dep.register_policy(
        required=[], clauses=[DETERMINISTIC_CLAUSE]
    )
    order_id = dep.record_order(policy_id)
    case_id = dep.open_case(order_id)
    dep.ready_case(case_id)

    dep.mock_llm(LLM_PROMPT_PATTERN, llm_reply(verdict="NOT_ELIGIBLE"))
    with dep.as_stranger():
        dep.contract.evaluate_case(case_id)

    assessment = dep.contract.get_assessment_history(case_id)[0]
    assert assessment["verdict"] == "ELIGIBLE_FULL"
    assert dep.llm_hits() == 0
    # The assessment shows which clause was enforced by which check.
    assert "CLAUSE:C1:REQUIRED_EVIDENCE:PASS" in assessment["deterministic_results"]


def test_missing_required_evidence_cannot_yield_a_full_refund(deployed):
    dep = deployed
    policy_id = dep.register_policy(required=["PHOTO_URL"], clauses=[INTERPRETIVE_CLAUSE])
    order_id = dep.record_order(policy_id)
    case_id = dep.open_case(order_id)
    dep.ready_case(case_id)

    # The model claims a full refund although the required photo is missing.
    dep.mock_llm(LLM_PROMPT_PATTERN, llm_reply(verdict="ELIGIBLE_FULL"))
    with dep.as_stranger():
        with dep.vm.expect_revert(
            "LLM_ERROR: verdict inconsistent with deterministic checks"
        ):
            dep.contract.evaluate_case(case_id)

    assert dep.contract.get_assessment_history(case_id) == []


def test_missing_required_evidence_cannot_yield_a_rejection_either(deployed):
    dep = deployed
    policy_id = dep.register_policy(required=["PHOTO_URL"], clauses=[INTERPRETIVE_CLAUSE])
    order_id = dep.record_order(policy_id)
    case_id = dep.open_case(order_id)
    dep.ready_case(case_id)

    # A missing document is not a finding against the buyer, so the model may
    # not reject the request either: the case stays open.
    dep.mock_llm(LLM_PROMPT_PATTERN, llm_reply(verdict="NOT_ELIGIBLE"))
    with dep.as_stranger():
        with dep.vm.expect_revert(
            "LLM_ERROR: verdict inconsistent with deterministic checks"
        ):
            dep.contract.evaluate_case(case_id)

    assert dep.contract.get_assessment_history(case_id) == []


def test_missing_required_evidence_with_a_consistent_verdict_is_recorded(deployed):
    dep = deployed
    policy_id = dep.register_policy(required=["PHOTO_URL"], clauses=[INTERPRETIVE_CLAUSE])
    order_id = dep.record_order(policy_id)
    case_id = dep.open_case(order_id)
    dep.ready_case(case_id)

    dep.mock_llm(LLM_PROMPT_PATTERN, llm_reply(verdict="INCONCLUSIVE"))
    with dep.as_stranger():
        dep.contract.evaluate_case(case_id)

    assessment = dep.contract.get_assessment_history(case_id)[0]
    assert "REQUIRED_EVIDENCE:FAIL" in assessment["deterministic_results"]
    assert assessment["verdict"] == "INCONCLUSIVE"
    assert "PROOF_REQUIREMENT_UNMET" in assessment["flags"]


def test_the_sellers_evidence_cannot_satisfy_the_buyers_proof_requirement(deployed):
    dep = deployed
    policy_id = dep.register_policy(required=["PHOTO_URL"], clauses=[INTERPRETIVE_CLAUSE])
    order_id = dep.record_order(policy_id)
    case_id = dep.open_case(order_id)

    # The merchant submits the photo the policy demands on the buyer.
    dep.ready_case(case_id, seller_evidence="a photo from the shop")

    dep.mock_llm(LLM_PROMPT_PATTERN, llm_reply(verdict="INCONCLUSIVE"))
    with dep.as_stranger():
        dep.contract.evaluate_case(case_id)

    assessment = dep.contract.get_assessment_history(case_id)[0]
    assert "REQUIRED_EVIDENCE:FAIL" in assessment["deterministic_results"]
    assert "PROOF_REQUIREMENT_UNMET" in assessment["flags"]


def test_fee_within_the_policy_max_is_accepted(deployed):
    dep = deployed
    policy_id = dep.register_policy(
        max_fee=1500, required=[], clauses=[INTERPRETIVE_CLAUSE]
    )
    order_id = dep.record_order(policy_id)
    case_id = dep.open_case(order_id)
    dep.ready_case(case_id)

    dep.mock_llm(
        LLM_PROMPT_PATTERN,
        llm_reply(verdict="ELIGIBLE_PARTIAL", fee_bps=1000),
    )
    with dep.as_stranger():
        dep.contract.evaluate_case(case_id)

    assessment = dep.contract.get_assessment_history(case_id)[0]
    assert assessment["verdict"] == "ELIGIBLE_PARTIAL"
    assert assessment["fee_bps"] == 1000
    # The fee is a deduction: the net refund is the rest of the price.
    assert assessment["net_refund_bps"] == 9000


def test_fee_above_the_policy_max_is_rejected(deployed):
    dep = deployed
    policy_id = dep.register_policy(max_fee=1500, clauses=[INTERPRETIVE_CLAUSE])
    order_id = dep.record_order(policy_id)
    case_id = dep.open_case(order_id)
    dep.ready_case(case_id)

    dep.mock_llm(
        LLM_PROMPT_PATTERN,
        llm_reply(verdict="ELIGIBLE_PARTIAL", fee_bps=2000),
    )
    with dep.as_stranger():
        with dep.vm.expect_revert("LLM_ERROR: fee outside policy bounds"):
            dep.contract.evaluate_case(case_id)

    assert dep.contract.get_assessment_history(case_id) == []


def test_negative_fee_is_rejected(deployed):
    dep = deployed
    policy_id = dep.register_policy(max_fee=1500, clauses=[INTERPRETIVE_CLAUSE])
    order_id = dep.record_order(policy_id)
    case_id = dep.open_case(order_id)
    dep.ready_case(case_id)

    dep.mock_llm(
        LLM_PROMPT_PATTERN,
        llm_reply(verdict="ELIGIBLE_PARTIAL", fee_bps=-100),
    )
    with dep.as_stranger():
        with dep.vm.expect_revert("LLM_ERROR: fee outside policy bounds"):
            dep.contract.evaluate_case(case_id)


def test_seller_silence_is_recorded_but_does_not_decide_the_case(deployed):
    dep = deployed
    policy_id = dep.register_policy(clauses=[INTERPRETIVE_CLAUSE])
    order_id = dep.record_order(policy_id, delivered_at="2026-01-01T00:00:00Z")
    dep.warp("2026-01-02T00:00:00Z")
    case_id = dep.open_case(order_id)

    with dep.as_buyer():
        dep.contract.submit_evidence(
            case_id, "TEXT_STATEMENT", "The device arrived defective."
        )
        dep.contract.request_seller_response(case_id)

    # The seller never answers, the window closes.
    dep.warp("2026-01-06T00:00:00Z")
    with dep.as_stranger():
        dep.contract.close_response_window(case_id)
    assert dep.contract.get_case_status(case_id) == "READY"

    dep.mock_llm(LLM_PROMPT_PATTERN, llm_reply(verdict="ELIGIBLE_FULL"))
    with dep.as_stranger():
        dep.contract.evaluate_case(case_id)

    assessment = dep.contract.get_assessment_history(case_id)[0]
    assert "SELLER_NO_RESPONSE" in assessment["flags"]
    # The silence did not decide the case: the model still produced a verdict.
    assert assessment["verdict"] == "ELIGIBLE_FULL"
    assert dep.llm_hits() >= 1


def test_a_case_cannot_be_assessed_before_the_response_window_is_closed(deployed):
    dep = deployed
    policy_id = dep.register_policy(clauses=[INTERPRETIVE_CLAUSE])
    order_id = dep.record_order(policy_id)
    case_id = dep.open_case(order_id)

    # The seller had no chance to answer yet.
    with dep.as_stranger():
        with dep.vm.expect_revert(
            "EXPECTED: seller response window is not closed yet"
        ):
            dep.contract.evaluate_case(case_id)

    dep.request_seller_response(case_id)
    with dep.as_stranger():
        with dep.vm.expect_revert(
            "EXPECTED: seller response window is not closed yet"
        ):
            dep.contract.evaluate_case(case_id)

    # Once the window is closed the case may be assessed.
    dep.close_seller_window(case_id)
    dep.mock_llm(LLM_PROMPT_PATTERN, llm_reply(verdict="INCONCLUSIVE"))
    with dep.as_stranger():
        dep.contract.evaluate_case(case_id)
    assert dep.contract.get_case_status(case_id) == "EVALUATED"


def test_evaluation_requires_a_valid_state(deployed):
    dep = deployed
    policy_id = dep.register_policy()
    order_id = dep.record_order(policy_id)
    case_id = dep.open_case(order_id)

    with dep.as_stranger():
        with dep.vm.expect_revert("EXPECTED: case not found"):
            dep.contract.evaluate_case("CAS-999")

    # A case can only be assessed once, from READY.
    dep.ready_case(case_id)
    dep.mock_llm(LLM_PROMPT_PATTERN, llm_reply(verdict="INCONCLUSIVE"))
    with dep.as_stranger():
        dep.contract.evaluate_case(case_id)

    with dep.as_stranger():
        with dep.vm.expect_revert("EXPECTED: invalid state transition"):
            dep.contract.evaluate_case(case_id)
