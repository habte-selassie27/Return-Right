"""Order records: pinning, trust assumptions and bounds."""

from tests.conftest import hex_address


def test_record_order_pins_the_policy_version(deployed):
    dep = deployed
    policy_id = dep.register_policy()
    order_id = dep.record_order(policy_id, version=1)

    order = dep.contract.get_order(order_id)
    assert order["order_id"] == order_id
    assert order["policy_id"] == policy_id
    assert order["policy_version"] == 1
    assert order["buyer"] == dep.buyer.lower()
    assert order["merchant"] == dep.merchant.lower()
    assert order["category_id"] == "ELECTRONICS"
    assert order["price"] == 10000
    assert order["delivered_at"] == "2026-01-01T00:00:00Z"


def test_order_stays_pinned_when_the_policy_is_updated(deployed):
    dep = deployed
    policy_id = dep.register_policy()
    order_id = dep.record_order(policy_id, version=1)

    with dep.as_merchant():
        dep.contract.update_policy(
            policy_id,
            "Extended returns",
            518400,
            [],
            ["TEXT_STATEMENT"],
            2000,
            [
                {
                    "clause_id": "C1",
                    "text": "Item must be unused.",
                    "kind": "DETERMINISTIC",
                    "topic": "CONDITION",
                    "rule": "RETURN_WINDOW",
                }
            ],
        )

    # The order keeps pointing at version 1 of the policy.
    order = dep.contract.get_order(order_id)
    assert order["policy_version"] == 1
    pinned = dep.contract.get_policy_version(policy_id, 1)
    assert pinned["version"] == 1
    assert pinned["max_restocking_bps"] == 1500


def test_buyer_cannot_equal_merchant(deployed):
    dep = deployed
    policy_id = dep.register_policy()
    with dep.as_merchant():
        with dep.vm.expect_revert("EXPECTED: buyer and merchant cannot be the same"):
            dep.contract.record_order(
                policy_id,
                1,
                dep.merchant,
                "ELECTRONICS",
                100,
                "2026-01-01T00:00:00Z",
                "https://shop.example/item/1",
            )


def test_merchant_cannot_record_against_another_merchants_policy(deployed):
    dep = deployed
    policy_id = dep.register_policy()
    with dep.as_stranger():
        with dep.vm.expect_revert("EXPECTED: caller is not authorized"):
            dep.contract.record_order(
                policy_id,
                1,
                dep.buyer,
                "ELECTRONICS",
                100,
                "2026-01-01T00:00:00Z",
                "https://shop.example/item/1",
            )


def test_record_order_validates_its_input(deployed):
    dep = deployed
    policy_id = dep.register_policy()

    with dep.as_merchant():
        with dep.vm.expect_revert("EXPECTED: policy not found"):
            dep.contract.record_order(
                "POL-999",
                1,
                dep.buyer,
                "ELECTRONICS",
                100,
                "2026-01-01T00:00:00Z",
                "https://shop.example/item/1",
            )

    with dep.as_merchant():
        with dep.vm.expect_revert("EXPECTED: policy version not found"):
            dep.contract.record_order(
                policy_id,
                7,
                dep.buyer,
                "ELECTRONICS",
                100,
                "2026-01-01T00:00:00Z",
                "https://shop.example/item/1",
            )

    with dep.as_merchant():
        with dep.vm.expect_revert("EXPECTED: invalid delivery timestamp"):
            dep.contract.record_order(
                policy_id,
                1,
                dep.buyer,
                "ELECTRONICS",
                100,
                "not-a-timestamp",
                "https://shop.example/item/1",
            )

    with dep.as_merchant():
        with dep.vm.expect_revert("EXPECTED: listing reference too long"):
            dep.contract.record_order(
                policy_id,
                1,
                dep.buyer,
                "ELECTRONICS",
                100,
                "2026-01-01T00:00:00Z",
                "x" * 513,
            )

    with dep.as_merchant():
        with dep.vm.expect_revert("EXPECTED: invalid address"):
            dep.contract.record_order(
                policy_id,
                1,
                "not-an-address",
                "ELECTRONICS",
                100,
                "2026-01-01T00:00:00Z",
                "https://shop.example/item/1",
            )


def test_unknown_order_reads_empty(deployed):
    dep = deployed
    assert dep.contract.get_order("ORD-999") == {}
