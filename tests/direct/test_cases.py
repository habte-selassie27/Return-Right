"""Cases, evidence and the case lifecycle."""

from tests.conftest import hex_address


def _setup(dep, reason="DEFECTIVE"):
    policy_id = dep.register_policy()
    order_id = dep.record_order(policy_id)
    case_id = dep.open_case(order_id, reason=reason)
    return policy_id, order_id, case_id


def test_open_case_only_by_the_order_buyer(deployed):
    dep = deployed
    policy_id = dep.register_policy()
    order_id = dep.record_order(policy_id)

    with dep.as_stranger():
        with dep.vm.expect_revert("EXPECTED: caller is not the order buyer"):
            dep.contract.open_case(order_id, "DEFECTIVE", "broken")

    with dep.as_merchant():
        with dep.vm.expect_revert("EXPECTED: caller is not the order buyer"):
            dep.contract.open_case(order_id, "DEFECTIVE", "broken")

    case_id = dep.open_case(order_id)
    case = dep.contract.get_case(case_id)
    assert case["status"] == "OPEN"
    assert case["reason"] == "DEFECTIVE"
    assert case["buyer"] == dep.buyer.lower()
    assert case["merchant"] == dep.merchant.lower()
    assert case["challenge_count"] == 0


def test_open_case_validates_input(deployed):
    dep = deployed
    policy_id = dep.register_policy()
    order_id = dep.record_order(policy_id)

    with dep.as_buyer():
        with dep.vm.expect_revert("EXPECTED: order not found"):
            dep.contract.open_case("ORD-999", "DEFECTIVE", "broken")

    with dep.as_buyer():
        with dep.vm.expect_revert("EXPECTED: unknown return reason"):
            dep.contract.open_case(order_id, "BECAUSE", "broken")

    with dep.as_buyer():
        with dep.vm.expect_revert("EXPECTED: invalid claim text"):
            dep.contract.open_case(order_id, "DEFECTIVE", "")

    with dep.as_buyer():
        with dep.vm.expect_revert("EXPECTED: invalid claim text"):
            dep.contract.open_case(order_id, "DEFECTIVE", "x" * 1001)


def test_only_one_live_case_per_order(deployed):
    dep = deployed
    policy_id = dep.register_policy()
    order_id = dep.record_order(policy_id)
    dep.open_case(order_id)

    with dep.as_buyer():
        with dep.vm.expect_revert("EXPECTED: order already has an open case"):
            dep.contract.open_case(order_id, "DEFECTIVE", "again")


def test_submit_evidence_derives_the_side_from_the_caller(deployed):
    dep = deployed
    _, _, case_id = _setup(dep)

    with dep.as_buyer():
        evidence_id = dep.contract.submit_evidence(
            case_id, "TEXT_STATEMENT", "The device does not power on."
        )
    with dep.as_buyer():
        dep.contract.request_seller_response(case_id)
    with dep.as_merchant():
        dep.contract.submit_evidence(
            case_id, "TEXT_STATEMENT", "The device was working when shipped."
        )

    items = dep.contract.get_evidence(case_id)
    assert len(items) == 2
    by_id = {item["evidence_id"]: item for item in items}
    assert by_id[evidence_id]["side"] == "BUYER"
    assert by_id[evidence_id]["submitted_by"] == dep.buyer.lower()
    other = [item for item in items if item["evidence_id"] != evidence_id][0]
    assert other["side"] == "SELLER"


def test_third_parties_cannot_submit_evidence(deployed):
    dep = deployed
    _, _, case_id = _setup(dep)
    with dep.as_stranger():
        with dep.vm.expect_revert("EXPECTED: caller is not a party to this case"):
            dep.contract.submit_evidence(case_id, "TEXT_STATEMENT", "hello")


def test_evidence_is_validated_and_capped_per_side(deployed):
    dep = deployed
    _, _, case_id = _setup(dep)

    with dep.as_buyer():
        with dep.vm.expect_revert("EXPECTED: unknown evidence kind"):
            dep.contract.submit_evidence(case_id, "SMELL", "x")

    with dep.as_buyer():
        with dep.vm.expect_revert("EXPECTED: invalid evidence reference"):
            dep.contract.submit_evidence(case_id, "TEXT_STATEMENT", "")

    with dep.as_buyer():
        with dep.vm.expect_revert("EXPECTED: invalid evidence reference"):
            dep.contract.submit_evidence(case_id, "TEXT_STATEMENT", "x" * 513)

    with dep.as_buyer():
        with dep.vm.expect_revert("EXPECTED: invalid evidence reference"):
            dep.contract.submit_evidence(case_id, "PHOTO_URL", "not-a-url")

    # The per-side cap is 8 and applies to the buyer.
    with dep.as_buyer():
        for index in range(8):
            dep.contract.submit_evidence(case_id, "TEXT_STATEMENT", "claim %d" % index)
    with dep.as_buyer():
        with dep.vm.expect_revert("EXPECTED: evidence limit reached"):
            dep.contract.submit_evidence(case_id, "TEXT_STATEMENT", "too many")

    assert len(dep.contract.get_evidence(case_id)) == 8


def test_evidence_is_append_only(deployed):
    dep = deployed
    _, _, case_id = _setup(dep)

    with dep.as_buyer():
        first = dep.contract.submit_evidence(case_id, "TEXT_STATEMENT", "first claim")
    with dep.as_buyer():
        second = dep.contract.submit_evidence(case_id, "TEXT_STATEMENT", "second claim")

    items = dep.contract.get_evidence(case_id)
    assert [item["evidence_id"] for item in items] == [first, second]
    assert items[0]["ref"] == "first claim"
    assert items[1]["ref"] == "second claim"

    # The contract exposes no way to remove or rewrite an evidence item.
    public_methods = set(dir(dep.contract))
    assert not any(
        name.startswith(("remove_", "delete_", "edit_", "replace_")) for name in public_methods
    )


def test_seller_may_only_respond_inside_the_response_window(deployed):
    dep = deployed
    _, _, case_id = _setup(dep)

    # Before the window is opened the seller has no right to respond.
    with dep.as_merchant():
        with dep.vm.expect_revert("EXPECTED: invalid state transition"):
            dep.contract.submit_evidence(case_id, "TEXT_STATEMENT", "too early")

    with dep.as_buyer():
        dep.contract.request_seller_response(case_id)
    assert dep.contract.get_case_status(case_id) == "AWAITING_SELLER"

    with dep.as_merchant():
        dep.contract.submit_evidence(case_id, "TEXT_STATEMENT", "in time")
    assert dep.contract.get_case(case_id)["seller_responded"] is True


def test_late_evidence_is_rejected_for_both_sides(deployed):
    dep = deployed
    policy_id = dep.register_policy()
    order_id = dep.record_order(policy_id, delivered_at="2026-01-01T00:00:00Z")
    dep.warp("2026-01-01T00:00:00Z")
    case_id = dep.open_case(order_id)

    with dep.as_buyer():
        dep.contract.request_seller_response(case_id)

    # Move past both windows (the window is 3 days by default).
    dep.warp("2026-01-10T00:00:00Z")

    with dep.as_buyer():
        with dep.vm.expect_revert("EXPECTED: evidence window closed"):
            dep.contract.submit_evidence(case_id, "TEXT_STATEMENT", "too late")

    with dep.as_merchant():
        with dep.vm.expect_revert("EXPECTED: response window closed"):
            dep.contract.submit_evidence(case_id, "TEXT_STATEMENT", "too late")


def test_seller_response_window_lifecycle(deployed):
    dep = deployed
    policy_id = dep.register_policy()
    order_id = dep.record_order(policy_id, delivered_at="2026-01-01T00:00:00Z")
    dep.warp("2026-01-01T00:00:00Z")
    case_id = dep.open_case(order_id)

    with dep.as_buyer():
        dep.contract.request_seller_response(case_id)

    # The window is still open: only the merchant may close it early.
    with dep.as_stranger():
        with dep.vm.expect_revert("EXPECTED: response window is still open"):
            dep.contract.close_response_window(case_id)

    with dep.as_merchant():
        dep.contract.close_response_window(case_id)
    assert dep.contract.get_case_status(case_id) == "READY"


def test_withdraw_case_only_by_the_buyer_before_evaluation(deployed):
    dep = deployed
    _, _, case_id = _setup(dep)

    with dep.as_merchant():
        with dep.vm.expect_revert("EXPECTED: caller is not the buyer"):
            dep.contract.withdraw_case(case_id)

    with dep.as_buyer():
        dep.contract.withdraw_case(case_id)
    assert dep.contract.get_case_status(case_id) == "WITHDRAWN"

    # A withdrawn case is terminal.
    with dep.as_buyer():
        with dep.vm.expect_revert("EXPECTED: invalid state transition"):
            dep.contract.withdraw_case(case_id)

    with dep.as_buyer():
        with dep.vm.expect_revert("EXPECTED: case is terminal"):
            dep.contract.submit_evidence(case_id, "TEXT_STATEMENT", "late")


def test_unknown_case_reads_empty(deployed):
    dep = deployed
    assert dep.contract.get_case("CAS-999") == {}
    assert dep.contract.get_case_status("CAS-999") == ""
    assert dep.contract.get_evidence("CAS-999") == []
    assert dep.contract.get_assessment_history("CAS-999") == []
