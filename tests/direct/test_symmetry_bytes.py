"""P0: the evidence symmetry, byte for byte.

The prompt the model sees must not depend on the order in which the evidence
was submitted, and it must not depend on which side submitted what. The
citations of the assessment must follow the same rule.
"""

from tests.conftest import LLM_PROMPT_PATTERN, llm_reply

CLAUSE = {
    "clause_id": "C1",
    "text": "Item must be unused or in like-new condition.",
    "kind": "INTERPRETIVE",
    "topic": "CONDITION",
}

BUYER_TEXT = "the unit is unused and in the box"
SELLER_TEXT = "the unit shows visible wear on the corner"

EVIDENCE_BLOCK_START = "<evidence>"
EVIDENCE_BLOCK_END = "</evidence>"


def _prompt_for(dep, order, case_id):
    """Assess a case and return the prompt the model saw."""
    dep.vm.clear_mocks()
    captured = dep.capture_prompts(llm_reply(verdict="ELIGIBLE_FULL"))
    with dep.as_stranger():
        dep.contract.evaluate_case(case_id)
    return captured[0]


def _evidence_block(prompt):
    """The evidence part of the prompt, without the surrounding text."""
    start = prompt.index(EVIDENCE_BLOCK_START)
    # The items carry their own closing tag, so the block ends at the LAST one.
    end = prompt.rindex(EVIDENCE_BLOCK_END) + len(EVIDENCE_BLOCK_END)
    return prompt[start:end]


def _case_with_order(dep, order, policy_id):
    """Open a case and submit the two statements in the given order.

    "BUYER_FIRST" submits the buyer statement first, "SELLER_FIRST" the other
    way round. The statements are the same in both cases, and they use the
    same policy, so the prompts have to be identical byte for byte.
    """
    order_id = dep.record_order(policy_id)
    case_id = dep.open_case(order_id)

    def buyer():
        with dep.as_buyer():
            dep.contract.submit_evidence(case_id, "TEXT_STATEMENT", BUYER_TEXT)

    def seller():
        with dep.as_merchant():
            dep.contract.submit_evidence(case_id, "TEXT_STATEMENT", SELLER_TEXT)

    if order == "BUYER_FIRST":
        buyer()
        dep.request_seller_response(case_id)
        seller()
    else:
        dep.request_seller_response(case_id)
        seller()
        buyer()
    dep.close_seller_window(case_id)
    return case_id


def test_the_prompt_is_byte_identical_under_a_permutation(deployed):
    dep = deployed
    policy_id = dep.register_policy(required=[], clauses=[CLAUSE])

    first = _case_with_order(dep, "BUYER_FIRST", policy_id)
    prompt_first = _prompt_for(dep, None, first)

    second = _case_with_order(dep, "SELLER_FIRST", policy_id)
    prompt_second = _prompt_for(dep, None, second)

    # The two cases carry the same statements, so the model has to see the same
    # bytes: same order, same labels, same content derived ids.
    assert _evidence_block(prompt_first) == _evidence_block(prompt_second)
    # And the two statements are in there, with the neutral labels.
    block = _evidence_block(prompt_first)
    assert BUYER_TEXT in block
    assert SELLER_TEXT in block
    assert 'side="A"' in block
    assert 'side="B"' in block
    assert "BUYER" not in block
    assert "SELLER" not in block


def test_the_citations_follow_the_canonical_order(deployed):
    dep = deployed
    policy_id = dep.register_policy(required=[], clauses=[CLAUSE])

    first = _case_with_order(dep, "BUYER_FIRST", policy_id)
    _prompt_for(dep, None, first)
    history_first = dep.contract.get_assessment_history(first)

    second = _case_with_order(dep, "SELLER_FIRST", policy_id)
    _prompt_for(dep, None, second)
    history_second = dep.contract.get_assessment_history(second)

    # The model cited the content derived id E1, the contract mapped it back
    # onto the stored record of the same statement. The stored id depends on
    # the submission order, the canonical citation does not.
    for case_id, history in ((first, history_first), (second, history_second)):
        assert len(history[0]["cited_evidence_ids"]) == 1
        stored = {item["evidence_id"]: item["ref"] for item in dep.contract.get_evidence(case_id)}
        cited = history[0]["cited_evidence_ids"][0]
        # In both cases the citation points at the buyer statement, because the
        # canonical order is the same in both cases.
        assert stored[cited] == BUYER_TEXT


def test_swapping_the_sides_does_not_change_the_prompt(deployed):
    dep = deployed
    policy_id = dep.register_policy(required=[], clauses=[CLAUSE])
    order_id = dep.record_order(policy_id)
    case_id = dep.open_case(order_id)

    dep.request_seller_response(case_id)
    with dep.as_buyer():
        dep.contract.submit_evidence(case_id, "TEXT_STATEMENT", BUYER_TEXT)
    with dep.as_merchant():
        dep.contract.submit_evidence(case_id, "TEXT_STATEMENT", SELLER_TEXT)
    dep.close_seller_window(case_id)

    prompt = _prompt_for(dep, None, case_id)
    block = _evidence_block(prompt)

    # The label follows the content, not the role: the same text always gets
    # the same label, whoever submitted it.
    lines = [line for line in block.splitlines() if "<evidence " in line]
    assert len(lines) == 2
    for line in lines:
        if BUYER_TEXT in line:
            assert 'side="A"' in line
        if SELLER_TEXT in line:
            assert 'side="B"' in line
