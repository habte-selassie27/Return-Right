"""Smoke test for the direct harness: deploy, register a policy, record an order."""

from tests.conftest import hex_address


def test_deploy_and_register(deployed):
    dep = deployed
    assert dep.contract.get_config()["owner"] == dep.owner.lower()

    with dep.as_merchant():
        policy_id = dep.contract.register_policy(
            "Standard returns",
            259200,
            [],
            ["TEXT_STATEMENT"],
            1500,
            [
                {
                    "clause_id": "C1",
                    "text": "Item must be unused or in like-new condition.",
                    "kind": "INTERPRETIVE",
                    "topic": "CONDITION",
                }
            ],
        )
    assert policy_id == "POL-0"

    policy = dep.contract.get_policy(policy_id)
    assert policy["title"] == "Standard returns"
    assert policy["version"] == 1
    assert policy["merchant"] == dep.merchant.lower()
    assert policy["clauses"][0]["clause_id"] == "C1"
    assert policy["status"] == "ACTIVE"
