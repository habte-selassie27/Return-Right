"""Two-sided symmetry: no ordering, labelling or limit may favour one party."""

import re

from tests.conftest import LLM_PROMPT_PATTERN, llm_reply

CLAUSE = {
    "clause_id": "C1",
    "text": "Item must be unused or in like-new condition.",
    "kind": "INTERPRETIVE",
    "topic": "CONDITION",
}

EVIDENCE_LINE = re.compile(
    r'<evidence id="([^"]+)" kind="([^"]+)" side="([^"]+)">([^<]*)</evidence>'
)


def _item(evidence_id, kind, ref, side):
    """A stand-in for a stored evidence item."""

    class Item:
        pass

    item = Item()
    item.evidence_id = evidence_id
    item.kind = kind
    item.ref = ref
    item.side = side
    return item


def test_permuting_the_evidence_does_not_change_the_prompt_order(contract_module):
    items = [
        _item("EV-0", "TEXT_STATEMENT", "buyer says it is unused", "BUYER"),
        _item("EV-1", "PHOTO_URL", "https://photos.example/a.png", "BUYER"),
        _item("EV-2", "TEXT_STATEMENT", "seller says it is worn", "SELLER"),
    ]

    expected = contract_module.canonical_evidence_order(items)
    assert len(expected) == 3

    # Every permutation of the input yields exactly the same rendering.
    import itertools

    for permutation in itertools.permutations(items):
        assert contract_module.canonical_evidence_order(list(permutation)) == expected


def test_swapping_the_sides_does_not_change_the_prompt_order(contract_module):
    buyer_item = _item("EV-0", "TEXT_STATEMENT", "the buyer statement", "BUYER")
    seller_item = _item("EV-1", "TEXT_STATEMENT", "the seller statement", "SELLER")

    original = contract_module.canonical_evidence_order([buyer_item, seller_item])
    swapped = contract_module.canonical_evidence_order(
        [
            _item("EV-0", "TEXT_STATEMENT", "the buyer statement", "SELLER"),
            _item("EV-1", "TEXT_STATEMENT", "the seller statement", "BUYER"),
        ]
    )

    # The label follows the evidence, not the role that submitted it.
    assert [entry[3] for entry in original] == [entry[3] for entry in swapped]
    assert [entry[1] for entry in original] == [entry[1] for entry in swapped]


def test_the_prompt_uses_neutral_labels_and_a_stable_order(deployed):
    dep = deployed
    policy_id = dep.register_policy(required=[], clauses=[CLAUSE])
    order_id = dep.record_order(policy_id)
    case_id = dep.open_case(order_id)

    with dep.as_buyer():
        dep.contract.submit_evidence(case_id, "TEXT_STATEMENT", "alpha statement")
        dep.contract.request_seller_response(case_id)
    with dep.as_merchant():
        dep.contract.submit_evidence(case_id, "TEXT_STATEMENT", "beta statement")
        dep.contract.close_response_window(case_id)

    captured = dep.capture_prompts(llm_reply(verdict="INCONCLUSIVE"))
    with dep.as_stranger():
        dep.contract.evaluate_case(case_id)

    assert len(captured) == 1
    prompt = captured[0]

    lines = [line for line in prompt.splitlines() if "<evidence " in line]
    assert len(lines) == 2
    sides = set()
    for line in lines:
        match = EVIDENCE_LINE.search(line)
        assert match is not None
        sides.add(match.group(3))
        # The prompt never names the parties.
        # The contract never names the parties, only neutral labels.
        assert "BUYER" not in line
        assert "SELLER" not in line
    assert sides == {"A", "B"}


def test_the_prompt_never_shows_a_stored_evidence_id(deployed):
    dep = deployed
    policy_id = dep.register_policy(required=[], clauses=[CLAUSE])
    order_id = dep.record_order(policy_id)
    case_id = dep.open_case(order_id)

    with dep.as_buyer():
        dep.contract.submit_evidence(case_id, "TEXT_STATEMENT", "alpha statement")
        dep.contract.request_seller_response(case_id)
    with dep.as_merchant():
        dep.contract.submit_evidence(case_id, "TEXT_STATEMENT", "beta statement")
        dep.contract.close_response_window(case_id)

    captured = dep.capture_prompts(llm_reply(verdict="INCONCLUSIVE"))
    with dep.as_stranger():
        dep.contract.evaluate_case(case_id)

    prompt = captured[0]
    # The stored ids are assigned in submission order, so they must not reach
    # the model: the prompt uses the content derived ids instead.
    assert "EV-0" not in prompt
    assert "EV-1" not in prompt
    for line in prompt.splitlines():
        if "<evidence " in line:
            assert EVIDENCE_LINE.search(line).group(1).startswith("E")


def test_the_order_of_the_evidence_in_the_prompt_does_not_depend_on_submission_order(
    deployed,
):
    dep = deployed
    policy_id = dep.register_policy(required=[], clauses=[CLAUSE])
    order_id = dep.record_order(policy_id)

    # First case: the buyer speaks first.
    case_one = dep.open_case(order_id)
    with dep.as_buyer():
        dep.contract.submit_evidence(case_one, "TEXT_STATEMENT", "alpha statement")
        dep.contract.request_seller_response(case_one)
    with dep.as_merchant():
        dep.contract.submit_evidence(case_one, "TEXT_STATEMENT", "beta statement")
        dep.contract.close_response_window(case_one)

    captured_one = dep.capture_prompts(llm_reply(verdict="INCONCLUSIVE"))
    with dep.as_stranger():
        dep.contract.evaluate_case(case_one)
    order_one = [
        EVIDENCE_LINE.search(line).group(3) + ":" + EVIDENCE_LINE.search(line).group(4)
        for line in captured_one[0].splitlines()
        if "<evidence " in line
    ]
    ids_one = [
        EVIDENCE_LINE.search(line).group(1)
        for line in captured_one[0].splitlines()
        if "<evidence " in line
    ]

    # Second case: the same two statements, submitted in the opposite order.
    order_id_two = dep.record_order(policy_id)
    case_two = dep.open_case(order_id_two)
    with dep.as_buyer():
        dep.contract.request_seller_response(case_two)
    with dep.as_merchant():
        dep.contract.submit_evidence(case_two, "TEXT_STATEMENT", "beta statement")
    with dep.as_buyer():
        dep.contract.submit_evidence(case_two, "TEXT_STATEMENT", "alpha statement")
    with dep.as_merchant():
        dep.contract.close_response_window(case_two)

    captured_two = dep.capture_prompts(llm_reply(verdict="INCONCLUSIVE"))
    with dep.as_stranger():
        dep.contract.evaluate_case(case_two)
    order_two = [
        EVIDENCE_LINE.search(line).group(3) + ":" + EVIDENCE_LINE.search(line).group(4)
        for line in captured_two[0].splitlines()
        if "<evidence " in line
    ]
    ids_two = [
        EVIDENCE_LINE.search(line).group(1)
        for line in captured_two[0].splitlines()
        if "<evidence " in line
    ]

    # The very same statements reach the model in the very same order, under
    # the very same content derived ids.
    assert order_one == order_two
    assert ids_one == ids_two


def test_both_sides_have_the_same_evidence_cap(deployed):
    dep = deployed
    policy_id = dep.register_policy()
    order_id = dep.record_order(policy_id)
    case_id = dep.open_case(order_id)

    with dep.as_buyer():
        for index in range(8):
            dep.contract.submit_evidence(case_id, "TEXT_STATEMENT", "buyer %d" % index)
    with dep.as_buyer():
        with dep.vm.expect_revert("EXPECTED: evidence limit reached"):
            dep.contract.submit_evidence(case_id, "TEXT_STATEMENT", "buyer 8")

    with dep.as_buyer():
        dep.contract.request_seller_response(case_id)
    with dep.as_merchant():
        for index in range(8):
            dep.contract.submit_evidence(case_id, "TEXT_STATEMENT", "seller %d" % index)
    with dep.as_merchant():
        with dep.vm.expect_revert("EXPECTED: evidence limit reached"):
            dep.contract.submit_evidence(case_id, "TEXT_STATEMENT", "seller 8")


def test_both_sides_have_the_same_window_length(deployed):
    dep = deployed
    policy_id = dep.register_policy()
    order_id = dep.record_order(policy_id, delivered_at="2026-01-01T00:00:00Z")
    dep.warp("2026-01-02T00:00:00Z")
    case_id = dep.open_case(order_id)

    with dep.as_buyer():
        dep.contract.request_seller_response(case_id)

    case = dep.contract.get_case(case_id)
    window = dep.contract.get_config()["seller_response_window_seconds"]

    from tests.conftest import DEFAULT_NOW

    assert case["evidence_deadline_at"] == "2026-01-05T00:00:00Z"
    assert case["seller_deadline_at"] == "2026-01-05T00:00:00Z"
    assert window == 259200


def test_both_sides_have_the_same_challenge_rights(deployed):
    dep = deployed
    policy_id = dep.register_policy(required=[], clauses=[CLAUSE])
    order_id = dep.record_order(policy_id)
    case_id = dep.open_case(order_id)
    dep.ready_case(case_id)
    dep.mock_llm(LLM_PROMPT_PATTERN, llm_reply(verdict="NOT_ELIGIBLE"))
    with dep.as_stranger():
        dep.contract.evaluate_case(case_id)

    # The buyer may challenge ...
    with dep.as_buyer():
        dep.contract.challenge_assessment(
            case_id, "The buyer adds a photo of the boxed unit."
        )
    assert dep.contract.get_case_status(case_id) == "CHALLENGED"

    # ... and so may the merchant, with the same window and the same rounds.
    dep.mock_llm(LLM_PROMPT_PATTERN, llm_reply(verdict="INCONCLUSIVE"))
    with dep.as_stranger():
        dep.contract.re_evaluate(case_id)
    with dep.as_merchant():
        dep.contract.challenge_assessment(
            case_id, "The merchant disputes the condition of the unit."
        )
    assert dep.contract.get_case_status(case_id) == "CHALLENGED"
