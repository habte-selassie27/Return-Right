"""The merchant recorded order data and the buyer's right to contest it.

The merchant records the delivery date and the category of an order, so both
are merchant assertions and not facts the contract can prove. A contested field
is never silently turned into a hard failure: the check becomes CONTESTED and
the validators decide the case on the evidence.
"""

from tests.conftest import LLM_PROMPT_PATTERN, llm_reply

CLAUSE = {
    "clause_id": "C1",
    "text": "Item must be unused or in like-new condition.",
    "kind": "INTERPRETIVE",
    "topic": "CONDITION",
}


def _case(dep, delivered_at="2026-01-01T00:00:00Z", category="ELECTRONICS"):
    policy_id = dep.register_policy(required=[], clauses=[CLAUSE])
    order_id = dep.record_order(
        policy_id, delivered_at=delivered_at, category=category
    )
    return dep.open_case(order_id)


def test_only_the_buyer_may_contest_the_order_record(deployed):
    dep = deployed
    case_id = _case(dep)

    for actor in ("merchant", "stranger", "owner"):
        with getattr(dep, "as_%s" % actor)():
            with dep.vm.expect_revert("EXPECTED: caller is not the buyer"):
                dep.contract.contest_order_record(case_id, ["DELIVERY_DATE"])


def test_an_unknown_contested_field_is_rejected(deployed):
    dep = deployed
    case_id = _case(dep)

    with dep.as_buyer():
        with dep.vm.expect_revert("EXPECTED: unknown contested field"):
            dep.contract.contest_order_record(case_id, ["PRICE"])

    with dep.as_buyer():
        with dep.vm.expect_revert("EXPECTED: invalid contested fields"):
            dep.contract.contest_order_record(case_id, [])


def test_a_contested_delivery_date_is_not_a_hard_failure(deployed):
    dep = deployed
    case_id = _case(dep, delivered_at="2025-12-01T00:00:00Z")

    with dep.as_buyer():
        dep.contract.contest_order_record(case_id, ["DELIVERY_DATE"])
    dep.ready_case(case_id)

    dep.mock_llm(LLM_PROMPT_PATTERN, llm_reply(verdict="ELIGIBLE_FULL"))
    with dep.as_stranger():
        dep.contract.evaluate_case(case_id)

    assessment = dep.contract.get_assessment_history(case_id)[0]
    # The check is contested, not failed, so the model was asked.
    assert "RETURN_WINDOW:CONTESTED" in assessment["deterministic_results"]
    assert "HARD_FAIL" not in assessment["flags"]
    assert "ORDER_RECORD_CONTESTED" in assessment["flags"]
    assert assessment["verdict"] == "ELIGIBLE_FULL"
    assert dep.llm_hits() >= 1


def test_a_contested_category_is_not_a_hard_failure(deployed):
    dep = deployed
    case_id = _case(dep, category="PERISHABLE")
    policy_id = dep.contract.get_case(case_id)["order_id"]

    with dep.as_buyer():
        dep.contract.contest_order_record(case_id, ["CATEGORY"])
    dep.ready_case(case_id)

    dep.mock_llm(LLM_PROMPT_PATTERN, llm_reply(verdict="INCONCLUSIVE"))
    with dep.as_stranger():
        dep.contract.evaluate_case(case_id)

    assessment = dep.contract.get_assessment_history(case_id)[0]
    assert "EXCLUDED_CATEGORY:CONTESTED" in assessment["deterministic_results"]
    assert "HARD_FAIL" not in assessment["flags"]
    assert assessment["verdict"] == "INCONCLUSIVE"
    assert policy_id is not None


def test_the_contested_field_is_shown_to_the_validators(deployed):
    dep = deployed
    case_id = _case(dep, delivered_at="2025-12-01T00:00:00Z")

    with dep.as_buyer():
        dep.contract.contest_order_record(case_id, ["DELIVERY_DATE"])
    dep.ready_case(case_id)

    captured = dep.capture_prompts(llm_reply(verdict="INCONCLUSIVE"))
    with dep.as_stranger():
        dep.contract.evaluate_case(case_id)

    prompt = captured[0]
    assert '<contested field="DELIVERY_DATE"/>' in prompt
    assert 'result="CONTESTED"' in prompt
    # The case view shows the contestation as well.
    assert dep.contract.get_case(case_id)["contested_fields"] == ["DELIVERY_DATE"]


def test_a_contested_record_without_an_interpretive_clause_stays_open(deployed):
    dep = deployed
    policy_id = dep.register_policy(
        required=[],
        clauses=[
            {
                "clause_id": "C1",
                "text": "The request must be inside the return window.",
                "kind": "DETERMINISTIC",
                "topic": "WINDOW",
                "rule": "RETURN_WINDOW",
            }
        ],
    )
    order_id = dep.record_order(policy_id, delivered_at="2025-12-01T00:00:00Z")
    case_id = dep.open_case(order_id)

    with dep.as_buyer():
        dep.contract.contest_order_record(case_id, ["DELIVERY_DATE"])
    dep.ready_case(case_id)

    dep.mock_llm(LLM_PROMPT_PATTERN, llm_reply(verdict="ELIGIBLE_FULL"))
    with dep.as_stranger():
        dep.contract.evaluate_case(case_id)

    assessment = dep.contract.get_assessment_history(case_id)[0]
    # The code cannot decide a contested field and there is no clause the
    # validators could weigh, so the case stays open for escalation.
    assert assessment["verdict"] == "INCONCLUSIVE"
    assert "ORDER_RECORD_CONTESTED" in assessment["flags"]
    assert dep.llm_hits() == 0


def test_a_case_may_not_be_contested_after_the_assessment(deployed):
    dep = deployed
    case_id = _case(dep)
    dep.ready_case(case_id)
    dep.mock_llm(LLM_PROMPT_PATTERN, llm_reply(verdict="INCONCLUSIVE"))
    with dep.as_stranger():
        dep.contract.evaluate_case(case_id)

    with dep.as_buyer():
        with dep.vm.expect_revert("EXPECTED: invalid state transition"):
            dep.contract.contest_order_record(case_id, ["DELIVERY_DATE"])
