"""P0: the proof the policy requires has to be established, not just present.

A required kind of evidence is only satisfied when the evidence is not just
PRESENT but also AVAILABLE: a link that cannot be reached does not prove
anything.
"""

from tests.conftest import LLM_PROMPT_PATTERN, llm_reply

INTERPRETIVE_CLAUSE = {
    "clause_id": "C1",
    "text": "Item must be unused or in like-new condition.",
    "kind": "INTERPRETIVE",
    "topic": "CONDITION",
}

DETERMINISTIC_CLAUSE = {
    "clause_id": "C1",
    "text": "A photo of the defect is required.",
    "kind": "DETERMINISTIC",
    "topic": "PROOF",
    "rule": "REQUIRED_EVIDENCE",
}

PHOTO_URL = "https://photos.example/defect.png"


def _case(dep, clauses=None, required=None):
    policy_id = dep.register_policy(
        required=["PHOTO_URL"] if required is None else required,
        clauses=clauses,
    )
    order_id = dep.record_order(policy_id)
    return dep.open_case(order_id)


def test_an_unreachable_required_photo_does_not_satisfy_the_policy(deployed):
    dep = deployed
    case_id = _case(dep, clauses=[INTERPRETIVE_CLAUSE])

    with dep.as_buyer():
        dep.contract.submit_evidence(case_id, "PHOTO_URL", PHOTO_URL)
    dep.ready_case(case_id)

    # The photo host cannot be reached: the proof is present but not available.
    dep.mock_llm(LLM_PROMPT_PATTERN, llm_reply(verdict="INCONCLUSIVE"))
    with dep.as_stranger():
        dep.contract.evaluate_case(case_id)

    assessment = dep.contract.get_assessment_history(case_id)[0]
    # The presence is recorded, the availability is not.
    assert "REQUIRED_EVIDENCE:PASS" in assessment["deterministic_results"]
    assert "REQUIRED_EVIDENCE_AVAILABLE:FAIL" in assessment["deterministic_results"]
    assert "PROOF_REQUIREMENT_UNMET" in assessment["flags"]
    assert "EVIDENCE_UNAVAILABLE" in assessment["flags"]
    assert assessment["verdict"] == "INCONCLUSIVE"


def test_a_deterministic_policy_does_not_pay_out_on_an_unreachable_proof(deployed):
    dep = deployed
    case_id = _case(dep, clauses=[DETERMINISTIC_CLAUSE])

    with dep.as_buyer():
        dep.contract.submit_evidence(case_id, "PHOTO_URL", PHOTO_URL)
    dep.ready_case(case_id)

    dep.mock_llm(LLM_PROMPT_PATTERN, llm_reply(verdict="ELIGIBLE_FULL"))
    with dep.as_stranger():
        dep.contract.evaluate_case(case_id)

    assessment = dep.contract.get_assessment_history(case_id)[0]
    # The code must not return a full refund for a proof it could not reach.
    assert assessment["verdict"] == "INCONCLUSIVE"
    assert "PROOF_REQUIREMENT_UNMET" in assessment["flags"]
    assert "DETERMINISTIC_SCOPE" not in assessment["flags"]


def test_a_reachable_required_photo_satisfies_the_policy(deployed):
    dep = deployed
    case_id = _case(dep, clauses=[INTERPRETIVE_CLAUSE])

    with dep.as_buyer():
        dep.contract.submit_evidence(case_id, "PHOTO_URL", PHOTO_URL)
    dep.ready_case(case_id)

    dep.mock_web("photos.example", 200, "binary-image-bytes")
    dep.mock_llm(LLM_PROMPT_PATTERN, llm_reply(verdict="ELIGIBLE_FULL"))
    with dep.as_stranger():
        dep.contract.evaluate_case(case_id)

    assessment = dep.contract.get_assessment_history(case_id)[0]
    assert "REQUIRED_EVIDENCE_AVAILABLE:PASS" in assessment["deterministic_results"]
    assert "PROOF_REQUIREMENT_UNMET" not in assessment["flags"]
    assert assessment["verdict"] == "ELIGIBLE_FULL"


def test_an_irrelevant_page_does_not_satisfy_a_photo_requirement(deployed):
    dep = deployed
    case_id = _case(dep, clauses=[DETERMINISTIC_CLAUSE])

    with dep.as_buyer():
        dep.contract.submit_evidence(case_id, "PHOTO_URL", PHOTO_URL)
    dep.ready_case(case_id)

    # The host answers, but with a page that is not a photo at all. The
    # contract does not analyze the image, so the proof stays unverified: the
    # assessment says so instead of pretending the photo was checked.
    dep.mock_web("photos.example", 200, "<html>not a photo</html>")
    dep.mock_llm(LLM_PROMPT_PATTERN, llm_reply(verdict="ELIGIBLE_FULL"))
    with dep.as_stranger():
        dep.contract.evaluate_case(case_id)

    assessment = dep.contract.get_assessment_history(case_id)[0]
    assert "EVIDENCE_UNVERIFIED" in assessment["flags"]
    # A reachable but unanalyzed photo is available, so the proof requirement is
    # met, and the assessment states that the image was not analyzed.
    assert "REQUIRED_EVIDENCE_AVAILABLE:PASS" in assessment["deterministic_results"]


def test_a_statement_satisfies_a_text_requirement(deployed):
    dep = deployed
    policy_id = dep.register_policy(required=["TEXT_STATEMENT"], clauses=[INTERPRETIVE_CLAUSE])
    order_id = dep.record_order(policy_id)
    case_id = dep.open_case(order_id)

    with dep.as_buyer():
        dep.contract.submit_evidence(case_id, "TEXT_STATEMENT", "the unit is broken")
    dep.ready_case(case_id)

    dep.mock_llm(LLM_PROMPT_PATTERN, llm_reply(verdict="ELIGIBLE_FULL"))
    with dep.as_stranger():
        dep.contract.evaluate_case(case_id)

    assessment = dep.contract.get_assessment_history(case_id)[0]
    assert "REQUIRED_EVIDENCE_AVAILABLE:PASS" in assessment["deterministic_results"]
    assert assessment["verdict"] == "ELIGIBLE_FULL"


def test_the_sellers_photo_does_not_satisfy_the_buyers_requirement(deployed):
    dep = deployed
    case_id = _case(dep, clauses=[DETERMINISTIC_CLAUSE])

    # The merchant submits the photo the policy demands on the buyer.
    dep.ready_case(case_id, seller_evidence="a photo from the shop")
    dep.mock_web("photos.example", 200, "binary-image-bytes")
    dep.mock_llm(LLM_PROMPT_PATTERN, llm_reply(verdict="ELIGIBLE_FULL"))
    with dep.as_stranger():
        dep.contract.evaluate_case(case_id)

    assessment = dep.contract.get_assessment_history(case_id)[0]
    assert "REQUIRED_EVIDENCE:FAIL" in assessment["deterministic_results"]
    assert "PROOF_REQUIREMENT_UNMET" in assessment["flags"]
    assert assessment["verdict"] == "INCONCLUSIVE"
