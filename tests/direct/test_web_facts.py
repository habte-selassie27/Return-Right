"""Call B: the structured claims extracted from linked evidence."""

from tests.conftest import LLM_PROMPT_PATTERN, llm_reply

CLAUSE = {
    "clause_id": "C1",
    "text": "Item must be unused or in like-new condition.",
    "kind": "INTERPRETIVE",
    "topic": "CONDITION",
}

TRACKING_URL = "https://carrier.example/track/12345"


def _case_with_tracking_evidence(dep, url=TRACKING_URL):
    policy_id = dep.register_policy(required=[], clauses=[CLAUSE])
    order_id = dep.record_order(policy_id)
    case_id = dep.open_case(order_id)
    with dep.as_buyer():
        dep.contract.submit_evidence(case_id, "TRACKING_URL", url)
    dep.ready_case(case_id)
    return case_id


def test_tracking_claims_are_extracted_and_passed_to_the_model(deployed):
    dep = deployed
    case_id = _case_with_tracking_evidence(dep)
    dep.mock_web("carrier.example/track", 200, "Status: Delivered on 2026-01-05")

    captured = dep.capture_prompts(llm_reply(verdict="ELIGIBLE_FULL"))
    with dep.as_stranger():
        dep.contract.evaluate_case(case_id)

    prompt = captured[0]
    assert 'delivery_claim="delivered"' in prompt
    assert 'delivery_day_claim="2026-01-05"' in prompt
    assert 'reachable="yes"' in prompt
    # The contract cannot authenticate the page, so the claim is unverified.
    assert 'source_trust="UNVERIFIED"' in prompt
    # The inspected page is fingerprinted for the audit trail.
    assert "content_digest=" in prompt


def test_an_unreachable_source_is_flagged_instead_of_deciding_the_case(deployed):
    dep = deployed
    case_id = _case_with_tracking_evidence(dep)
    # No web mock is registered, so the source cannot be reached.
    dep.mock_llm(LLM_PROMPT_PATTERN, llm_reply(verdict="INCONCLUSIVE"))

    with dep.as_stranger():
        dep.contract.evaluate_case(case_id)

    assessment = dep.contract.get_assessment_history(case_id)[0]
    assert "EVIDENCE_UNAVAILABLE" in assessment["flags"]
    # The case was still assessed, the evidence was only marked unavailable.
    assert assessment["verdict"] == "INCONCLUSIVE"


def test_a_changed_source_makes_the_validators_disagree(deployed):
    dep = deployed
    case_id = _case_with_tracking_evidence(dep)
    dep.mock_web("carrier.example/track", 200, "Status: Delivered on 2026-01-05")
    dep.mock_llm(LLM_PROMPT_PATTERN, llm_reply(verdict="ELIGIBLE_FULL"))

    with dep.as_stranger():
        dep.contract.evaluate_case(case_id)

    # The first captured block is the web facts, the second one the interpretation.
    validators = dep.vm._captured_validators
    assert len(validators) == 2
    facts_index = 0
    stored_facts = validators[facts_index][0]
    # The facts are keyed by the content derived evidence id, never by the
    # stored id, so the submission order cannot leak into the prompt.
    assert stored_facts["E1"]["delivery_claim"] == "delivered"

    # The same source now says something else: the validators must disagree.
    dep.vm.clear_mocks()
    dep.mock_web("carrier.example/track", 200, "Status: In transit since 2026-01-06")
    assert dep.vm.run_validator(index=facts_index, leader_result=stored_facts) is False

    # With the original page the validators agree again.
    dep.vm.clear_mocks()
    dep.mock_web("carrier.example/track", 200, "Status: Delivered on 2026-01-05")
    assert dep.vm.run_validator(index=facts_index, leader_result=stored_facts) is True


def test_a_photo_url_is_only_checked_for_reachability(deployed):
    dep = deployed
    policy_id = dep.register_policy(required=[], clauses=[CLAUSE])
    order_id = dep.record_order(policy_id)
    case_id = dep.open_case(order_id)
    with dep.as_buyer():
        dep.contract.submit_evidence(
            case_id, "PHOTO_URL", "https://photos.example/defect.png"
        )
    dep.ready_case(case_id)

    dep.mock_web("photos.example", 200, "binary-image-bytes")
    captured = dep.capture_prompts(llm_reply(verdict="ELIGIBLE_FULL"))
    with dep.as_stranger():
        dep.contract.evaluate_case(case_id)

    prompt = captured[0]
    # The contract never claims to have looked inside the image.
    assert 'content="not_analyzed"' in prompt
    assert "EVIDENCE_UNAVAILABLE" not in dep.contract.get_assessment_history(case_id)[0]["flags"]
    # A reachable source is still only an unverified claim.
    assert "EVIDENCE_UNVERIFIED" in dep.contract.get_assessment_history(case_id)[0]["flags"]
