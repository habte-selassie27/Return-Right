"""The case lifecycle: deadlines, boundaries and every state transition.

The exact sequence of the case is:

    OPEN -> AWAITING_SELLER -> READY -> EVALUATED -> CHALLENGED
         -> RE_EVALUATED -> ... -> FINALIZED
    any non-final state -> ESCALATED | WITHDRAWN
"""

from tests.conftest import LLM_PROMPT_PATTERN, llm_reply

CLAUSE = {
    "clause_id": "C1",
    "text": "Item must be unused or in like-new condition.",
    "kind": "INTERPRETIVE",
    "topic": "CONDITION",
}

CHALLENGE_REASON = (
    "The buyer uploaded a new photograph showing the unit is unused and boxed."
)

# The default window is three days, the challenge window two days.
WINDOW_END = "2026-01-05T00:00:00Z"


def _open(dep, required=None):
    policy_id = dep.register_policy(required=[] if required is None else required)
    order_id = dep.record_order(policy_id, delivered_at="2026-01-01T00:00:00Z")
    return dep.open_case(order_id)


def test_the_response_window_must_be_closed_before_an_assessment(deployed):
    dep = deployed
    case_id = _open(dep)

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


def test_the_response_window_can_only_be_opened_once(deployed):
    dep = deployed
    case_id = _open(dep)
    dep.request_seller_response(case_id)

    with dep.as_stranger():
        with dep.vm.expect_revert("EXPECTED: invalid state transition"):
            dep.contract.request_seller_response(case_id)


def test_the_response_window_can_only_be_closed_once(deployed):
    dep = deployed
    case_id = _open(dep)
    dep.request_seller_response(case_id)
    dep.close_seller_window(case_id)

    with dep.as_stranger():
        with dep.vm.expect_revert("EXPECTED: invalid state transition"):
            dep.contract.close_response_window(case_id)


def test_a_third_party_may_not_close_the_window_before_the_deadline(deployed):
    dep = deployed
    case_id = _open(dep)
    dep.request_seller_response(case_id)

    with dep.as_stranger():
        with dep.vm.expect_revert("EXPECTED: response window is still open"):
            dep.contract.close_response_window(case_id)

    # After the deadline anyone may close it, so nobody can stall a case.
    dep.warp("2026-01-06T00:00:00Z")
    with dep.as_stranger():
        dep.contract.close_response_window(case_id)
    assert dep.contract.get_case_status(case_id) == "READY"


def test_evidence_is_accepted_exactly_at_the_shared_deadline(deployed):
    dep = deployed
    case_id = _open(dep)
    dep.request_seller_response(case_id)

    dep.warp(WINDOW_END)
    with dep.as_buyer():
        dep.contract.submit_evidence(case_id, "TEXT_STATEMENT", "right on time")
    with dep.as_merchant():
        dep.contract.submit_evidence(case_id, "TEXT_STATEMENT", "right on time too")

    # One second later both sides are out of time.
    dep.warp("2026-01-05T00:00:01Z")
    with dep.as_buyer():
        with dep.vm.expect_revert("EXPECTED: evidence window closed"):
            dep.contract.submit_evidence(case_id, "TEXT_STATEMENT", "too late")
    with dep.as_merchant():
        with dep.vm.expect_revert("EXPECTED: response window closed"):
            dep.contract.submit_evidence(case_id, "TEXT_STATEMENT", "too late")


def test_the_evidence_deadline_moves_with_the_seller_window(deployed):
    dep = deployed
    case_id = _open(dep)

    # The seller is invited late, so the seller still gets a full window and
    # the buyer is not cut off before the seller answered.
    dep.warp("2026-01-04T00:00:00Z")
    dep.request_seller_response(case_id)

    case = dep.contract.get_case(case_id)
    assert case["seller_deadline_at"] == "2026-01-07T00:00:00Z"
    assert case["evidence_deadline_at"] == "2026-01-07T00:00:00Z"

    # The buyer can still answer the seller inside the shared deadline.
    dep.warp("2026-01-06T00:00:00Z")
    with dep.as_buyer():
        dep.contract.submit_evidence(case_id, "TEXT_STATEMENT", "the answer")
    with dep.as_merchant():
        dep.contract.submit_evidence(case_id, "TEXT_STATEMENT", "the counter answer")


def test_the_evidence_is_frozen_when_the_response_window_closes(deployed):
    dep = deployed
    case_id = _open(dep)
    dep.request_seller_response(case_id)
    dep.close_seller_window(case_id)

    # Neither side may slip in evidence after the other side answered.
    with dep.as_buyer():
        with dep.vm.expect_revert("EXPECTED: evidence window closed"):
            dep.contract.submit_evidence(case_id, "TEXT_STATEMENT", "too late")
    with dep.as_merchant():
        with dep.vm.expect_revert("EXPECTED: response window closed"):
            dep.contract.submit_evidence(case_id, "TEXT_STATEMENT", "too late")


def test_both_sides_may_add_evidence_inside_the_challenge_window(deployed):
    dep = deployed
    policy_id = dep.register_policy(required=[], clauses=[CLAUSE])
    order_id = dep.record_order(policy_id)
    case_id = dep.open_case(order_id)
    dep.ready_case(case_id)
    dep.mock_llm(LLM_PROMPT_PATTERN, llm_reply(verdict="NOT_ELIGIBLE"))
    with dep.as_stranger():
        dep.contract.evaluate_case(case_id)

    # The buyer challenges and adds the proof for the challenge ...
    with dep.as_buyer():
        dep.contract.challenge_assessment(case_id, CHALLENGE_REASON)
        dep.contract.submit_evidence(case_id, "TEXT_STATEMENT", "a new photo")

    # ... and so may the merchant, with exactly the same right.
    with dep.as_merchant():
        dep.contract.submit_evidence(case_id, "TEXT_STATEMENT", "a counter photo")

    assert len(dep.contract.get_evidence(case_id)) == 2


def test_a_terminal_case_accepts_nothing(deployed):
    dep = deployed
    policy_id = dep.register_policy(required=[], clauses=[CLAUSE])
    order_id = dep.record_order(policy_id)
    case_id = dep.open_case(order_id)
    dep.ready_case(case_id)
    dep.mock_llm(LLM_PROMPT_PATTERN, llm_reply(verdict="INCONCLUSIVE"))
    with dep.as_stranger():
        dep.contract.evaluate_case(case_id)

    dep.warp("2026-01-20T00:00:00Z")
    with dep.as_stranger():
        dep.contract.finalize_case(case_id)

    for action in (
        lambda: dep.contract.evaluate_case(case_id),
        lambda: dep.contract.challenge_assessment(case_id, CHALLENGE_REASON),
        lambda: dep.contract.re_evaluate(case_id),
        lambda: dep.contract.finalize_case(case_id),
    ):
        with dep.as_stranger():
            with dep.vm.expect_revert("EXPECTED: invalid state transition"):
                action()

    with dep.as_buyer():
        with dep.vm.expect_revert("EXPECTED: case is terminal"):
            dep.contract.submit_evidence(case_id, "TEXT_STATEMENT", "late")
    with dep.as_buyer():
        with dep.vm.expect_revert("EXPECTED: invalid state transition"):
            dep.contract.withdraw_case(case_id)


def test_a_case_may_only_be_assessed_once(deployed):
    dep = deployed
    policy_id = dep.register_policy(required=[], clauses=[CLAUSE])
    order_id = dep.record_order(policy_id)
    case_id = dep.open_case(order_id)
    dep.ready_case(case_id)
    dep.mock_llm(LLM_PROMPT_PATTERN, llm_reply(verdict="INCONCLUSIVE"))
    with dep.as_stranger():
        dep.contract.evaluate_case(case_id)

    with dep.as_stranger():
        with dep.vm.expect_revert("EXPECTED: invalid state transition"):
            dep.contract.evaluate_case(case_id)
    assert len(dep.contract.get_assessment_history(case_id)) == 1


def test_a_withdrawn_case_never_reaches_an_assessment(deployed):
    dep = deployed
    policy_id = dep.register_policy(required=[], clauses=[CLAUSE])
    order_id = dep.record_order(policy_id)
    case_id = dep.open_case(order_id)

    # The buyer may withdraw the case before it is assessed.
    with dep.as_buyer():
        dep.contract.withdraw_case(case_id)

    with dep.as_stranger():
        with dep.vm.expect_revert("EXPECTED: invalid state transition"):
            dep.contract.evaluate_case(case_id)
    assert dep.contract.get_assessment_history(case_id) == []


def test_the_response_window_can_be_closed_at_the_exact_deadline(deployed):
    dep = deployed
    case_id = _open(dep)
    dep.request_seller_response(case_id)

    # One second before the deadline the window is still open.
    dep.warp("2026-01-04T23:59:59Z")
    with dep.as_stranger():
        with dep.vm.expect_revert("EXPECTED: response window is still open"):
            dep.contract.close_response_window(case_id)

    # At the deadline it is over.
    dep.warp("2026-01-05T00:00:00Z")
    with dep.as_stranger():
        dep.contract.close_response_window(case_id)
    assert dep.contract.get_case_status(case_id) == "READY"


def test_a_late_invitation_is_rejected(deployed):
    dep = deployed
    case_id = _open(dep)

    # The invitation deadline is the initial evidence deadline, so the seller
    # can never be handed a window that starts after the case was stale.
    dep.warp("2026-01-05T00:00:01Z")
    with dep.as_stranger():
        with dep.vm.expect_revert("EXPECTED: invitation window closed"):
            dep.contract.request_seller_response(case_id)


def test_a_case_that_was_never_invited_can_be_closed_after_the_deadline(deployed):
    dep = deployed
    case_id = _open(dep)

    # Before the deadline nobody may close it: the seller still has to be
    # invited.
    with dep.as_stranger():
        with dep.vm.expect_revert("EXPECTED: response window is still open"):
            dep.contract.close_response_window(case_id)

    dep.warp("2026-01-05T00:00:01Z")
    with dep.as_stranger():
        dep.contract.close_response_window(case_id)
    assert dep.contract.get_case_status(case_id) == "READY"

    # The seller was never invited, so the case says so.
    dep.mock_llm(LLM_PROMPT_PATTERN, llm_reply(verdict="INCONCLUSIVE"))
    with dep.as_stranger():
        dep.contract.evaluate_case(case_id)
    assert "SELLER_NO_RESPONSE" in dep.contract.get_assessment_history(case_id)[0]["flags"]


def test_evidence_is_refused_after_an_assessment_without_a_challenge(deployed):
    dep = deployed
    policy_id = dep.register_policy(required=[], clauses=[CLAUSE])
    order_id = dep.record_order(policy_id)
    case_id = dep.open_case(order_id)
    dep.ready_case(case_id)
    dep.mock_llm(LLM_PROMPT_PATTERN, llm_reply(verdict="INCONCLUSIVE"))
    with dep.as_stranger():
        dep.contract.evaluate_case(case_id)

    # Evidence that is never weighed would be pointless, so it is refused
    # until a challenge is pending.
    for actor in ("buyer", "merchant"):
        with getattr(dep, "as_%s" % actor)():
            with dep.vm.expect_revert("EXPECTED: evidence window closed"):
                dep.contract.submit_evidence(case_id, "TEXT_STATEMENT", "too late")

    # With a pending challenge both sides may add their proof again.
    with dep.as_buyer():
        dep.contract.challenge_assessment(case_id, CHALLENGE_REASON)
    with dep.as_buyer():
        dep.contract.submit_evidence(case_id, "TEXT_STATEMENT", "the new photo")
    with dep.as_merchant():
        dep.contract.submit_evidence(case_id, "TEXT_STATEMENT", "the counter photo")
