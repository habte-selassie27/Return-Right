"""Leader and validator behaviour of the two non-deterministic calls.

The direct harness does not emulate a VM level consensus failure, so the tests
below drive the captured validator functions directly: that is exactly what the
validators do on chain, and a validator that accepts a bad leader result is the
bug these tests hunt.
"""

from tests.conftest import LLM_PROMPT_PATTERN, llm_reply

CLAUSE = {
    "clause_id": "C1",
    "text": "Item must be unused or in like-new condition.",
    "kind": "INTERPRETIVE",
    "topic": "CONDITION",
}


def _ready_case(dep):
    policy_id = dep.register_policy(required=[], clauses=[CLAUSE])
    order_id = dep.record_order(policy_id, delivered_at="2026-01-01T00:00:00Z")
    dep.warp("2026-01-02T00:00:00Z")
    case_id = dep.open_case(order_id)
    with dep.as_buyer():
        dep.contract.submit_evidence(case_id, "TEXT_STATEMENT", "The unit is unused.")
    dep.ready_case(case_id)
    return case_id


def test_the_validator_accepts_an_equivalent_leader_result(deployed):
    dep = deployed
    case_id = _ready_case(dep)
    dep.mock_llm(LLM_PROMPT_PATTERN, llm_reply(verdict="ELIGIBLE_FULL"))

    with dep.as_stranger():
        dep.contract.evaluate_case(case_id)

    # The last captured block is the interpretation.
    assert dep.run_last_validator() is True


def test_the_validator_rejects_a_different_verdict(deployed):
    dep = deployed
    case_id = _ready_case(dep)
    dep.mock_llm(LLM_PROMPT_PATTERN, llm_reply(verdict="ELIGIBLE_FULL"))

    with dep.as_stranger():
        dep.contract.evaluate_case(case_id)

    bad = {
        "verdict": "NOT_ELIGIBLE",
        "confidence_band": "MEDIUM",
        "fee_bps": 0,
        "cited_clause_ids": ["C1"],
        "cited_evidence_ids": [],
        "reasoning_digest": "a different decision",
    }
    assert dep.run_last_validator(leader_result=bad) is False


def test_the_validator_rejects_a_leader_result_with_an_illegal_fee(deployed):
    dep = deployed
    case_id = _ready_case(dep)
    dep.mock_llm(LLM_PROMPT_PATTERN, llm_reply(verdict="ELIGIBLE_FULL"))

    with dep.as_stranger():
        dep.contract.evaluate_case(case_id)

    bad = {
        "verdict": "ELIGIBLE_PARTIAL",
        "confidence_band": "MEDIUM",
        "fee_bps": 999999,
        "cited_clause_ids": ["C1"],
        "cited_evidence_ids": [],
        "reasoning_digest": "an illegal fee",
    }
    assert dep.run_last_validator(leader_result=bad) is False


def test_the_validator_rejects_a_hallucinated_evidence_id(deployed):
    dep = deployed
    case_id = _ready_case(dep)
    dep.mock_llm(LLM_PROMPT_PATTERN, llm_reply(verdict="ELIGIBLE_FULL"))

    with dep.as_stranger():
        dep.contract.evaluate_case(case_id)

    bad = {
        "verdict": "ELIGIBLE_FULL",
        "confidence_band": "MEDIUM",
        "fee_bps": 0,
        "cited_clause_ids": ["C1"],
        "cited_evidence_ids": ["E9"],
        "reasoning_digest": "an invented citation",
    }
    assert dep.run_last_validator(leader_result=bad) is False


def test_the_validator_rejects_a_leader_result_that_contradicts_the_checks(deployed):
    dep = deployed
    case_id = _ready_case(dep)
    dep.mock_llm(LLM_PROMPT_PATTERN, llm_reply(verdict="ELIGIBLE_FULL"))

    with dep.as_stranger():
        dep.contract.evaluate_case(case_id)

    # The policy requires a statement from the buyer. Without it the case may
    # not be decided on the merits.
    dep.vm.clear_mocks()
    dep.mock_llm(
        LLM_PROMPT_PATTERN, llm_reply(verdict="ELIGIBLE_FULL", evidence=[])
    )
    policy_id = dep.register_policy(required=["PHOTO_URL"], clauses=[CLAUSE])
    order_id = dep.record_order(policy_id, delivered_at="2026-01-01T00:00:00Z")
    other_case = dep.open_case(order_id)
    dep.ready_case(other_case)

    with dep.as_stranger():
        with dep.vm.expect_revert(
            "LLM_ERROR: verdict inconsistent with deterministic checks"
        ):
            dep.contract.evaluate_case(other_case)


def test_a_consensus_failure_is_never_an_inconclusive_verdict(deployed):
    dep = deployed
    case_id = _ready_case(dep)
    dep.mock_llm(LLM_PROMPT_PATTERN, llm_reply(verdict="ELIGIBLE_FULL"))

    with dep.as_stranger():
        dep.contract.evaluate_case(case_id)

    # The validators disagree with the leader: on chain the block fails and the
    # transaction is retried. The case keeps its state and no assessment is
    # appended, so a disagreement can never look like an INCONCLUSIVE verdict.
    bad = {
        "verdict": "NOT_ELIGIBLE",
        "confidence_band": "LOW",
        "fee_bps": 0,
        "cited_clause_ids": [],
        "cited_evidence_ids": [],
        "reasoning_digest": "disagreement",
    }
    assert dep.run_last_validator(leader_result=bad) is False

    history = dep.contract.get_assessment_history(case_id)
    assert len(history) == 1
    assert history[0]["verdict"] == "ELIGIBLE_FULL"


def test_the_validator_accepts_a_band_that_differs_by_one_step(deployed):
    dep = deployed
    case_id = _ready_case(dep)
    # The model answers LOW, that is what the validator derives itself.
    dep.mock_llm(LLM_PROMPT_PATTERN, llm_reply(verdict="ELIGIBLE_FULL", confidence="LOW"))

    with dep.as_stranger():
        dep.contract.evaluate_case(case_id)

    leader = {
        "verdict": "ELIGIBLE_FULL",
        "confidence_band": "MEDIUM",
        "fee_bps": 0,
        "cited_clause_ids": ["C1"],
        "cited_evidence_ids": ["E1"],
        "reasoning_digest": "the leader",
    }
    # The leader was one step more confident: the rule tolerates that.
    assert dep.run_last_validator(leader_result=leader) is True

    far = dict(leader)
    far["confidence_band"] = "HIGH"
    # Two steps apart: the rule does not tolerate that.
    assert dep.run_last_validator(leader_result=far) is False


def test_the_validator_rejects_a_fee_in_another_bucket(deployed):
    dep = deployed
    case_id = _ready_case(dep)
    # The model asks for a fee of 100 basis points.
    dep.mock_llm(
        LLM_PROMPT_PATTERN,
        llm_reply(verdict="ELIGIBLE_PARTIAL", fee_bps=100),
    )

    with dep.as_stranger():
        dep.contract.evaluate_case(case_id)

    leader = {
        "verdict": "ELIGIBLE_PARTIAL",
        "confidence_band": "MEDIUM",
        "fee_bps": 200,
        "cited_clause_ids": ["C1"],
        "cited_evidence_ids": ["E1"],
        "reasoning_digest": "a small fee",
    }
    # 200 and 100 land in the same coarse bucket.
    assert dep.run_last_validator(leader_result=leader) is True

    far = dict(leader)
    far["fee_bps"] = 900
    # 900 is a different bucket.
    assert dep.run_last_validator(leader_result=far) is False


def test_the_validator_rejects_a_leader_result_without_citations(deployed):
    """An eligible verdict without a citation is an unsupported claim."""
    dep = deployed
    case_id = _ready_case(dep)
    dep.mock_llm(LLM_PROMPT_PATTERN, llm_reply(verdict="ELIGIBLE_FULL"))

    with dep.as_stranger():
        dep.contract.evaluate_case(case_id)

    leader = {
        "verdict": "ELIGIBLE_FULL",
        "confidence_band": "MEDIUM",
        "fee_bps": 0,
        "cited_clause_ids": [],
        "cited_evidence_ids": [],
        "reasoning_digest": "no citation at all",
    }
    assert dep.run_last_validator(leader_result=leader) is False


def test_an_unavailable_evidence_fetch_is_not_a_verdict(deployed):
    """The source cannot be reached: the case is assessed, not decided."""
    dep = deployed
    policy_id = dep.register_policy(required=["TRACKING_URL"], clauses=[CLAUSE])
    order_id = dep.record_order(policy_id)
    case_id = dep.open_case(order_id)
    with dep.as_buyer():
        dep.contract.submit_evidence(
            case_id, "TRACKING_URL", "https://carrier.example/track/1"
        )
    dep.ready_case(case_id)

    # No web mock: the fetch fails.
    dep.mock_llm(LLM_PROMPT_PATTERN, llm_reply(verdict="INCONCLUSIVE"))
    with dep.as_stranger():
        dep.contract.evaluate_case(case_id)

    assessment = dep.contract.get_assessment_history(case_id)[0]
    assert "EVIDENCE_UNAVAILABLE" in assessment["flags"]
    assert "PROOF_REQUIREMENT_UNMET" in assessment["flags"]
    assert assessment["verdict"] == "INCONCLUSIVE"
    # The case is decided, the source was not.
    assert dep.contract.get_case_status(case_id) == "EVALUATED"
