"""Policy registry: versioning, bounds, deprecation and access control."""

from tests.conftest import hex_address


def test_register_policy_stores_version_1(deployed):
    dep = deployed
    policy_id = dep.register_policy()

    policy = dep.contract.get_policy(policy_id)
    assert policy["policy_id"] == policy_id
    assert policy["version"] == 1
    assert policy["merchant"] == dep.merchant.lower()
    assert policy["title"] == "Standard returns"
    assert policy["return_window_seconds"] == 259200
    assert policy["max_restocking_bps"] == 1500
    assert policy["status"] == "ACTIVE"
    assert policy["excluded_categories"] == []
    assert policy["required_evidence_kinds"] == ["TEXT_STATEMENT"]
    assert policy["clauses"][0]["kind"] == "INTERPRETIVE"
    assert policy["clauses"][0]["topic"] == "CONDITION"


def test_update_policy_creates_version_2(deployed):
    dep = deployed
    policy_id = dep.register_policy()

    with dep.as_merchant():
        version = dep.contract.update_policy(
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
    assert version == 2

    latest = dep.contract.get_policy(policy_id)
    assert latest["version"] == 2
    assert latest["title"] == "Extended returns"

    # The old version is still readable and unchanged: orders stay pinned.
    old = dep.contract.get_policy_version(policy_id, 1)
    assert old["version"] == 1
    assert old["title"] == "Standard returns"
    assert old["max_restocking_bps"] == 1500


def test_policy_bounds_are_enforced(deployed):
    dep = deployed
    clause = {
        "clause_id": "C1",
        "text": "text",
        "kind": "INTERPRETIVE",
        "topic": "OTHER",
    }

    with dep.as_merchant():
        with dep.vm.expect_revert("EXPECTED: too many clauses"):
            dep.contract.register_policy(
                "t", 100, [], [], 0, [clause] * 13
            )

    with dep.as_merchant():
        with dep.vm.expect_revert("EXPECTED: too many excluded categories"):
            dep.contract.register_policy(
                "t", 100, ["c"] * 9, [], 0, [clause]
            )

    with dep.as_merchant():
        with dep.vm.expect_revert("EXPECTED: too many required evidence kinds"):
            dep.contract.register_policy(
                "t", 100, [], ["TEXT_STATEMENT"] * 9, 0, [clause]
            )

    with dep.as_merchant():
        with dep.vm.expect_revert("EXPECTED: invalid policy title"):
            dep.contract.register_policy("", 100, [], [], 0, [clause])

    with dep.as_merchant():
        with dep.vm.expect_revert("EXPECTED: invalid policy title"):
            dep.contract.register_policy("x" * 201, 100, [], [], 0, [clause])

    with dep.as_merchant():
        with dep.vm.expect_revert("EXPECTED: invalid return window"):
            dep.contract.register_policy("t", 0, [], [], 0, [clause])

    with dep.as_merchant():
        with dep.vm.expect_revert("EXPECTED: invalid restocking fee"):
            dep.contract.register_policy("t", 100, [], [], 10001, [clause])

    with dep.as_merchant():
        with dep.vm.expect_revert("EXPECTED: a policy needs at least one clause"):
            dep.contract.register_policy("t", 100, [], [], 0, [])

    with dep.as_merchant():
        with dep.vm.expect_revert("EXPECTED: clause text too long"):
            dep.contract.register_policy(
                "t",
                100,
                [],
                [],
                0,
                [{"clause_id": "C1", "text": "x" * 501, "kind": "DETERMINISTIC"}],
            )

    with dep.as_merchant():
        with dep.vm.expect_revert("EXPECTED: unknown clause kind"):
            dep.contract.register_policy(
                "t", 100, [], [], 0, [{"clause_id": "C1", "text": "x", "kind": "FUZZY"}]
            )

    with dep.as_merchant():
        with dep.vm.expect_revert("EXPECTED: unknown clause topic"):
            dep.contract.register_policy(
                "t",
                100,
                [],
                [],
                0,
                [{"clause_id": "C1", "text": "x", "kind": "DETERMINISTIC", "topic": "NOPE"}],
            )

    with dep.as_merchant():
        with dep.vm.expect_revert("EXPECTED: unknown evidence kind"):
            dep.contract.register_policy("t", 100, [], ["SMELL"], 0, [clause])


def test_deprecate_policy_blocks_new_orders_only(deployed):
    dep = deployed
    policy_id = dep.register_policy()
    order_id = dep.record_order(policy_id)

    with dep.as_merchant():
        dep.contract.deprecate_policy(policy_id)

    assert dep.contract.get_policy(policy_id)["status"] == "DEPRECATED"

    # Existing orders stay usable ...
    case_id = dep.open_case(order_id)
    assert dep.contract.get_case_status(case_id) == "OPEN"

    # ... but no new order may use the deprecated policy.
    with dep.as_merchant():
        with dep.vm.expect_revert("EXPECTED: policy is deprecated"):
            dep.contract.record_order(
                policy_id,
                1,
                dep.buyer,
                "ELECTRONICS",
                100,
                "2026-01-01T00:00:00Z",
                "https://shop.example/item/2",
            )


def test_list_active_policies(deployed):
    dep = deployed
    first = dep.register_policy()
    second = dep.register_policy(title="Second")

    assert dep.contract.list_active_policies(dep.merchant.lower()) == [first, second]
    assert dep.contract.list_active_policies(dep.stranger.lower()) == []

    with dep.as_merchant():
        dep.contract.deprecate_policy(first)

    assert dep.contract.list_active_policies(dep.merchant.lower()) == [second]


def test_merchant_cannot_manage_another_merchants_policy(deployed):
    dep = deployed
    policy_id = dep.register_policy()

    with dep.as_stranger():
        with dep.vm.expect_revert("EXPECTED: caller is not authorized"):
            dep.contract.update_policy(
                policy_id,
                "Hijacked",
                100,
                [],
                [],
                0,
                [{"clause_id": "C1", "text": "x", "kind": "DETERMINISTIC"}],
            )

    with dep.as_stranger():
        with dep.vm.expect_revert("EXPECTED: caller is not authorized"):
            dep.contract.deprecate_policy(policy_id)


def test_a_merchant_cannot_register_an_unbounded_number_of_policies(deployed):
    dep = deployed
    clause = {
        "clause_id": "C1",
        "text": "text",
        "kind": "INTERPRETIVE",
        "topic": "OTHER",
    }
    with dep.as_merchant():
        for _ in range(64):
            dep.contract.register_policy("t", 100, [], [], 0, [clause])

    with dep.as_merchant():
        with dep.vm.expect_revert("EXPECTED: too many policies for this merchant"):
            dep.contract.register_policy("t", 100, [], [], 0, [clause])


def test_unknown_policy_is_rejected(deployed):
    dep = deployed
    with dep.as_merchant():
        with dep.vm.expect_revert("EXPECTED: policy not found"):
            dep.contract.deprecate_policy("POL-999")

    with dep.as_merchant():
        with dep.vm.expect_revert("EXPECTED: policy not found"):
            dep.contract.update_policy(
                "POL-999",
                "x",
                100,
                [],
                [],
                0,
                [{"clause_id": "C1", "text": "x", "kind": "DETERMINISTIC"}],
            )


def test_a_deterministic_clause_must_bind_to_an_enforced_rule(deployed):
    dep = deployed
    # A clause that claims to be deterministic but names no rule would never be
    # enforced by the code, so it is rejected instead of silently ignored.
    with dep.as_merchant():
        with dep.vm.expect_revert("EXPECTED: unsupported deterministic clause"):
            dep.contract.register_policy(
                "t",
                100,
                [],
                [],
                0,
                [
                    {
                        "clause_id": "C1",
                        "text": "The item must be blue.",
                        "kind": "DETERMINISTIC",
                        "topic": "OTHER",
                    }
                ],
            )

    with dep.as_merchant():
        with dep.vm.expect_revert("EXPECTED: unsupported deterministic clause"):
            dep.contract.register_policy(
                "t",
                100,
                [],
                [],
                0,
                [
                    {
                        "clause_id": "C1",
                        "text": "x",
                        "kind": "DETERMINISTIC",
                        "topic": "OTHER",
                        "rule": "BLUE_ITEM",
                    }
                ],
            )


def test_an_interpretive_clause_may_not_declare_a_rule(deployed):
    dep = deployed
    with dep.as_merchant():
        with dep.vm.expect_revert(
            "EXPECTED: interpretive clause cannot declare a rule"
        ):
            dep.contract.register_policy(
                "t",
                100,
                [],
                [],
                0,
                [
                    {
                        "clause_id": "C1",
                        "text": "x",
                        "kind": "INTERPRETIVE",
                        "topic": "OTHER",
                        "rule": "RETURN_WINDOW",
                    }
                ],
            )


def test_duplicate_clause_ids_are_rejected(deployed):
    dep = deployed
    with dep.as_merchant():
        with dep.vm.expect_revert("EXPECTED: duplicate clause id"):
            dep.contract.register_policy(
                "t",
                100,
                [],
                [],
                0,
                [
                    {
                        "clause_id": "C1",
                        "text": "first",
                        "kind": "INTERPRETIVE",
                        "topic": "OTHER",
                    },
                    {
                        "clause_id": "C1",
                        "text": "second",
                        "kind": "INTERPRETIVE",
                        "topic": "OTHER",
                    },
                ],
            )


def test_ambiguous_policy_lists_are_rejected(deployed):
    dep = deployed
    clause = {
        "clause_id": "C1",
        "text": "x",
        "kind": "INTERPRETIVE",
        "topic": "OTHER",
    }
    with dep.as_merchant():
        with dep.vm.expect_revert("EXPECTED: duplicate required evidence kind"):
            dep.contract.register_policy(
                "t", 100, [], ["TEXT_STATEMENT", "TEXT_STATEMENT"], 0, [clause]
            )

    with dep.as_merchant():
        with dep.vm.expect_revert("EXPECTED: duplicate excluded category"):
            dep.contract.register_policy(
                "t", 100, ["TOYS", "TOYS"], [], 0, [clause]
            )


def test_the_clause_rule_is_part_of_the_stored_policy(deployed):
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
    clause = dep.contract.get_policy(policy_id)["clauses"][0]
    assert clause["rule"] == "RETURN_WINDOW"
    assert clause["kind"] == "DETERMINISTIC"
