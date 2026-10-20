"""P0: the contested merchant record and the hard rejections.

A contested hard check disables EVERY hard rejection of the case: the merchant
recorded the whole order, so a dispute about one field puts the reliability of
the record in question.
"""

from tests.conftest import LLM_PROMPT_PATTERN, llm_reply

CLAUSE = {
    "clause_id": "C1",
    "text": "Item must be unused or in like-new condition.",
    "kind": "INTERPRETIVE",
    "topic": "CONDITION",
}

DETERMINISTIC_CLAUSE = {
    "clause_id": "C1",
    "text": "The request must be inside the return window.",
    "kind": "DETERMINISTIC",
    "topic": "WINDOW",
    "rule": "RETURN_WINDOW",
}


def _case(dep, delivered_at="2026-01-01T00:00:00Z", category="ELECTRONICS", clauses=None):
    policy_id = dep.register_policy(
        required=[], excluded=["PERISHABLE"], clauses=clauses or [CLAUSE]
    )
    order_id = dep.record_order(
        policy_id, delivered_at=delivered_at, category=category
    )
    return dep.open_case(order_id)


def test_a_contested_category_does_not_reject_the_case_on_the_delivery_date(deployed):
    """The case must not be rejected on the other field of the same record."""
    dep = deployed
    # The delivery date is far outside the return window.
    case_id = _case(dep, delivered_at="2025-12-01T00:00:00Z")

    with dep.as_buyer():
        dep.contract.contest_order_record(case_id, ["CATEGORY"])
        dep.contract.submit_evidence(
            case_id, "TEXT_STATEMENT", "the courier delivered it on 2025-12-28"
        )
    dep.ready_case(case_id)

    dep.mock_llm(LLM_PROMPT_PATTERN, llm_reply(verdict="ELIGIBLE_FULL"))
    with dep.as_stranger():
        dep.contract.evaluate_case(case_id)

    assessment = dep.contract.get_assessment_history(case_id)[0]
    # The hard failure is still recorded, but it no longer rejects the case.
    assert "RETURN_WINDOW:FAIL" in assessment["deterministic_results"]
    assert "HARD_FAIL" not in assessment["flags"]
    assert "ORDER_RECORD_CONTESTED" in assessment["flags"]
    assert assessment["verdict"] == "ELIGIBLE_FULL"
    assert dep.llm_hits() >= 1


def test_a_contested_delivery_date_does_not_reject_the_case_on_the_category(deployed):
    dep = deployed
    case_id = _case(dep, category="PERISHABLE")

    with dep.as_buyer():
        dep.contract.contest_order_record(case_id, ["DELIVERY_DATE"])
        dep.contract.submit_evidence(
            case_id, "TEXT_STATEMENT", "the unit is not a consumable"
        )
    dep.ready_case(case_id)

    dep.mock_llm(LLM_PROMPT_PATTERN, llm_reply(verdict="ELIGIBLE_FULL"))
    with dep.as_stranger():
        dep.contract.evaluate_case(case_id)

    assessment = dep.contract.get_assessment_history(case_id)[0]
    assert "EXCLUDED_CATEGORY:FAIL" in assessment["deterministic_results"]
    assert "HARD_FAIL" not in assessment["flags"]
    assert assessment["verdict"] == "ELIGIBLE_FULL"


def test_both_fields_may_be_contested_at_once(deployed):
    dep = deployed
    case_id = _case(dep, delivered_at="2025-12-01T00:00:00Z", category="PERISHABLE")

    with dep.as_buyer():
        dep.contract.contest_order_record(
            case_id, ["DELIVERY_DATE", "CATEGORY"]
        )
        dep.contract.submit_evidence(
            case_id, "TEXT_STATEMENT", "the courier delivered it on 2025-12-28"
        )
    dep.ready_case(case_id)

    dep.mock_llm(LLM_PROMPT_PATTERN, llm_reply(verdict="INCONCLUSIVE"))
    with dep.as_stranger():
        dep.contract.evaluate_case(case_id)

    assessment = dep.contract.get_assessment_history(case_id)[0]
    assert "RETURN_WINDOW:CONTESTED" in assessment["deterministic_results"]
    assert "EXCLUDED_CATEGORY:CONTESTED" in assessment["deterministic_results"]
    assert "HARD_FAIL" not in assessment["flags"]
    assert assessment["verdict"] == "INCONCLUSIVE"


def test_conflicting_evidence_about_a_contested_field_stays_open(deployed):
    dep = deployed
    case_id = _case(dep, delivered_at="2025-12-01T00:00:00Z")

    with dep.as_buyer():
        dep.contract.contest_order_record(case_id, ["DELIVERY_DATE"])
        dep.contract.submit_evidence(
            case_id, "TEXT_STATEMENT", "the courier delivered it on 2025-12-28"
        )
    dep.ready_case(case_id, seller_evidence="the courier delivered it on 2026-01-02")

    # The sides conflict about the date and the model cannot resolve it.
    dep.mock_llm(LLM_PROMPT_PATTERN, llm_reply(verdict="INCONCLUSIVE"))
    with dep.as_stranger():
        dep.contract.evaluate_case(case_id)

    assessment = dep.contract.get_assessment_history(case_id)[0]
    assert assessment["verdict"] == "INCONCLUSIVE"
    assert assessment["confidence_band"] == "MEDIUM"
    assert "ORDER_RECORD_CONTESTED" in assessment["flags"]


def test_a_contested_case_without_an_interpretive_clause_stays_open(deployed):
    dep = deployed
    case_id = _case(dep, delivered_at="2025-12-01T00:00:00Z", clauses=[DETERMINISTIC_CLAUSE])

    with dep.as_buyer():
        dep.contract.contest_order_record(case_id, ["DELIVERY_DATE"])
    dep.ready_case(case_id)

    dep.mock_llm(LLM_PROMPT_PATTERN, llm_reply(verdict="ELIGIBLE_FULL"))
    with dep.as_stranger():
        dep.contract.evaluate_case(case_id)

    assessment = dep.contract.get_assessment_history(case_id)[0]
    assert assessment["verdict"] == "INCONCLUSIVE"
    assert "ORDER_RECORD_CONTESTED" in assessment["flags"]
    # The code cannot decide a contested field, so it does not ask the model.
    assert dep.llm_hits() == 0
