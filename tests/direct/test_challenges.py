"""Challenges, re-evaluation, finality and escalation."""

from tests.conftest import LLM_PROMPT_PATTERN, llm_reply

INTERPRETIVE_CLAUSE = {
    "clause_id": "C1",
    "text": "Item must be unused or in like-new condition.",
    "kind": "INTERPRETIVE",
    "topic": "CONDITION",
}

CHALLENGE_REASON = (
    "The buyer uploaded a new photograph showing the unit is unused and boxed."
)


def _ready_case(dep):
    """A case with buyer and seller evidence that is ready for evaluation."""
    policy_id = dep.register_policy(required=[], clauses=[INTERPRETIVE_CLAUSE])
    order_id = dep.record_order(policy_id, delivered_at="2026-01-01T00:00:00Z")
    dep.warp("2026-01-02T00:00:00Z")
    case_id = dep.open_case(order_id)
    with dep.as_buyer():
        dep.contract.submit_evidence(case_id, "TEXT_STATEMENT", "The unit is unused.")
        dep.contract.request_seller_response(case_id)
    with dep.as_merchant():
        dep.contract.submit_evidence(
            case_id, "TEXT_STATEMENT", "The unit shows visible wear."
        )
        dep.contract.close_response_window(case_id)
    return case_id


def test_challenge_inside_the_window_is_accepted(deployed):
    dep = deployed
    case_id = _ready_case(dep)
    dep.mock_llm(LLM_PROMPT_PATTERN, llm_reply(verdict="NOT_ELIGIBLE"))
    with dep.as_stranger():
        dep.contract.evaluate_case(case_id)
    assert dep.contract.get_case_status(case_id) == "EVALUATED"

    with dep.as_buyer():
        dep.contract.challenge_assessment(case_id, CHALLENGE_REASON)
    assert dep.contract.get_case_status(case_id) == "CHALLENGED"
    assert dep.contract.get_case(case_id)["challenge_count"] == 1


def test_both_sides_may_challenge(deployed):
    dep = deployed
    case_id = _ready_case(dep)
    dep.mock_llm(LLM_PROMPT_PATTERN, llm_reply(verdict="NOT_ELIGIBLE"))
    with dep.as_stranger():
        dep.contract.evaluate_case(case_id)

    with dep.as_merchant():
        dep.contract.challenge_assessment(case_id, CHALLENGE_REASON)
    assert dep.contract.get_case_status(case_id) == "CHALLENGED"


def test_a_stranger_may_not_challenge(deployed):
    dep = deployed
    case_id = _ready_case(dep)
    dep.mock_llm(LLM_PROMPT_PATTERN, llm_reply(verdict="NOT_ELIGIBLE"))
    with dep.as_stranger():
        dep.contract.evaluate_case(case_id)

    with dep.as_stranger():
        with dep.vm.expect_revert("EXPECTED: caller is not authorized"):
            dep.contract.challenge_assessment(case_id, CHALLENGE_REASON)


def test_a_challenge_without_a_reason_is_rejected(deployed):
    dep = deployed
    case_id = _ready_case(dep)
    dep.mock_llm(LLM_PROMPT_PATTERN, llm_reply(verdict="NOT_ELIGIBLE"))
    with dep.as_stranger():
        dep.contract.evaluate_case(case_id)

    with dep.as_buyer():
        with dep.vm.expect_revert("EXPECTED: challenge reason too short"):
            dep.contract.challenge_assessment(case_id, "no")

    with dep.as_buyer():
        with dep.vm.expect_revert("EXPECTED: challenge reason too long"):
            dep.contract.challenge_assessment(case_id, "x" * 501)


def test_a_challenge_after_the_window_is_rejected(deployed):
    dep = deployed
    case_id = _ready_case(dep)
    dep.mock_llm(LLM_PROMPT_PATTERN, llm_reply(verdict="NOT_ELIGIBLE"))
    with dep.as_stranger():
        dep.contract.evaluate_case(case_id)

    # The challenge window is two days long.
    dep.warp("2026-01-20T00:00:00Z")
    with dep.as_buyer():
        with dep.vm.expect_revert("EXPECTED: challenge window closed"):
            dep.contract.challenge_assessment(case_id, CHALLENGE_REASON)


def test_the_number_of_challenge_rounds_is_bounded(deployed):
    dep = deployed
    case_id = _ready_case(dep)
    dep.mock_llm(LLM_PROMPT_PATTERN, llm_reply(verdict="NOT_ELIGIBLE"))
    with dep.as_stranger():
        dep.contract.evaluate_case(case_id)

    for _ in range(2):
        with dep.as_buyer():
            dep.contract.challenge_assessment(case_id, CHALLENGE_REASON)
        with dep.as_stranger():
            dep.contract.re_evaluate(case_id)

    with dep.as_buyer():
        with dep.vm.expect_revert("EXPECTED: challenge rounds exhausted"):
            dep.contract.challenge_assessment(case_id, CHALLENGE_REASON)


def test_a_challenge_appends_and_never_overwrites(deployed):
    dep = deployed
    case_id = _ready_case(dep)
    dep.mock_llm(LLM_PROMPT_PATTERN, llm_reply(verdict="NOT_ELIGIBLE", reasoning="first"))
    with dep.as_stranger():
        dep.contract.evaluate_case(case_id)

    first = dep.contract.get_assessment_history(case_id)
    assert len(first) == 1
    assert first[0]["produced_by"] == "EVALUATION"
    assert first[0]["round"] == 1

    with dep.as_buyer():
        dep.contract.challenge_assessment(case_id, CHALLENGE_REASON)

    # The buyer adds the new proof that triggered the challenge.
    with dep.as_buyer():
        dep.contract.submit_evidence(
            case_id, "TEXT_STATEMENT", "New photo of the boxed, unused unit."
        )

    # The re-evaluation sees the new evidence and cites it.
    dep.vm.clear_mocks()
    dep.mock_llm(
        LLM_PROMPT_PATTERN,
        llm_reply(verdict="ELIGIBLE_FULL", evidence=["EV-2"], reasoning="second"),
    )
    with dep.as_stranger():
        dep.contract.re_evaluate(case_id)

    history = dep.contract.get_assessment_history(case_id)
    assert len(history) == 2
    assert history[0]["verdict"] == "NOT_ELIGIBLE"
    assert history[0]["reasoning_digest"] == "first"
    assert history[1]["produced_by"] == "RE_EVALUATION"
    assert history[1]["round"] == 2
    assert history[1]["reasoning_digest"] == "second"
    assert "EV-2" in history[1]["cited_evidence_ids"]


def test_re_evaluate_requires_a_pending_challenge(deployed):
    dep = deployed
    case_id = _ready_case(dep)
    dep.mock_llm(LLM_PROMPT_PATTERN, llm_reply(verdict="NOT_ELIGIBLE"))
    with dep.as_stranger():
        dep.contract.evaluate_case(case_id)

    with dep.as_stranger():
        with dep.vm.expect_revert("EXPECTED: invalid state transition"):
            dep.contract.re_evaluate(case_id)


def test_finalize_is_blocked_while_the_challenge_window_is_open(deployed):
    dep = deployed
    case_id = _ready_case(dep)
    dep.mock_llm(LLM_PROMPT_PATTERN, llm_reply(verdict="NOT_ELIGIBLE"))
    with dep.as_stranger():
        dep.contract.evaluate_case(case_id)

    with dep.as_stranger():
        with dep.vm.expect_revert("EXPECTED: challenge window is still open"):
            dep.contract.finalize_case(case_id)

    dep.warp("2026-01-05T00:00:00Z")
    with dep.as_stranger():
        dep.contract.finalize_case(case_id)
    assert dep.contract.get_case_status(case_id) == "FINALIZED"

    # A finalized case is terminal.
    with dep.as_stranger():
        with dep.vm.expect_revert("EXPECTED: invalid state transition"):
            dep.contract.finalize_case(case_id)


def test_escalation_records_the_handoff_and_stops_the_case(deployed):
    dep = deployed
    case_id = _ready_case(dep)
    dep.mock_llm(LLM_PROMPT_PATTERN, llm_reply(verdict="INCONCLUSIVE"))
    with dep.as_stranger():
        dep.contract.evaluate_case(case_id)

    with dep.as_stranger():
        with dep.vm.expect_revert("EXPECTED: caller is not authorized"):
            dep.contract.escalate_case(case_id, "conflicting evidence")

    with dep.as_owner():
        dep.contract.escalate_case(case_id, "conflicting evidence")

    case = dep.contract.get_case(case_id)
    assert case["status"] == "ESCALATED"
    assert case["escalation_reason"] == "conflicting evidence"
    assert case["escalated_by"] == dep.owner.lower()
    # The assessment history is preserved for the human process.
    assert len(dep.contract.get_assessment_history(case_id)) == 1

    with dep.as_stranger():
        with dep.vm.expect_revert("EXPECTED: invalid state transition"):
            dep.contract.evaluate_case(case_id)


def test_escalation_role_can_escalate(deployed):
    dep = deployed
    case_id = _ready_case(dep)

    with dep.as_owner():
        dep.contract.set_escalation_role(dep.stranger)

    with dep.as_stranger():
        dep.contract.escalate_case(case_id, "needs a human")
    assert dep.contract.get_case_status(case_id) == "ESCALATED"
