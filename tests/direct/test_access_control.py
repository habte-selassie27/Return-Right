"""Every restricted method rejects an unauthorized caller."""

from tests.conftest import LLM_PROMPT_PATTERN, llm_reply

CLAUSE = {
    "clause_id": "C1",
    "text": "Item must be unused or in like-new condition.",
    "kind": "INTERPRETIVE",
    "topic": "CONDITION",
}


def test_only_the_owner_may_change_the_configuration(deployed):
    dep = deployed
    with dep.as_stranger():
        with dep.vm.expect_revert("EXPECTED: caller is not authorized"):
            dep.contract.set_config(1000, 1000, 1, 4)

    with dep.as_merchant():
        with dep.vm.expect_revert("EXPECTED: caller is not authorized"):
            dep.contract.set_config(1000, 1000, 1, 4)

    with dep.as_owner():
        dep.contract.set_config(1000, 1000, 1, 4)
    config = dep.contract.get_config()
    assert config["seller_response_window_seconds"] == 1000
    assert config["challenge_window_seconds"] == 1000
    assert config["max_challenge_rounds"] == 1
    assert config["max_evidence_per_side"] == 4


def test_only_the_owner_may_assign_the_escalation_role(deployed):
    dep = deployed
    with dep.as_stranger():
        with dep.vm.expect_revert("EXPECTED: caller is not authorized"):
            dep.contract.set_escalation_role(dep.stranger)

    with dep.as_owner():
        dep.contract.set_escalation_role(dep.stranger)
    assert dep.contract.get_config()["escalation_role"] == dep.stranger.lower()


def test_everyone_may_register_a_policy_but_only_own_their_own(deployed):
    dep = deployed
    # Registering a policy is open: every caller becomes the owner of it.
    with dep.as_stranger():
        policy_id = dep.contract.register_policy("t", 100, [], [], 0, [CLAUSE])
    assert dep.contract.get_policy(policy_id)["merchant"] == dep.stranger.lower()

    # But a policy of another merchant is off limits.
    merchant_policy = dep.register_policy()
    with dep.as_stranger():
        with dep.vm.expect_revert("EXPECTED: caller is not authorized"):
            dep.contract.update_policy(
                merchant_policy,
                "hijacked",
                100,
                [],
                [],
                0,
                [CLAUSE],
            )
    with dep.as_stranger():
        with dep.vm.expect_revert("EXPECTED: caller is not authorized"):
            dep.contract.deprecate_policy(merchant_policy)


def test_only_the_buyer_may_open_and_withdraw_a_case(deployed):
    dep = deployed
    policy_id = dep.register_policy()
    order_id = dep.record_order(policy_id)

    with dep.as_merchant():
        with dep.vm.expect_revert("EXPECTED: caller is not the order buyer"):
            dep.contract.open_case(order_id, "DEFECTIVE", "broken")

    case_id = dep.open_case(order_id)
    with dep.as_merchant():
        with dep.vm.expect_revert("EXPECTED: caller is not the buyer"):
            dep.contract.withdraw_case(case_id)


def test_only_the_parties_may_submit_evidence(deployed):
    dep = deployed
    policy_id = dep.register_policy()
    order_id = dep.record_order(policy_id)
    case_id = dep.open_case(order_id)

    with dep.as_stranger():
        with dep.vm.expect_revert("EXPECTED: caller is not a party to this case"):
            dep.contract.submit_evidence(case_id, "TEXT_STATEMENT", "hi")

    with dep.as_owner():
        with dep.vm.expect_revert("EXPECTED: caller is not a party to this case"):
            dep.contract.submit_evidence(case_id, "TEXT_STATEMENT", "hi")


def test_only_the_buyer_or_the_owner_may_request_a_seller_response(deployed):
    dep = deployed
    policy_id = dep.register_policy()
    order_id = dep.record_order(policy_id)
    case_id = dep.open_case(order_id)

    with dep.as_merchant():
        with dep.vm.expect_revert("EXPECTED: caller is not authorized"):
            dep.contract.request_seller_response(case_id)

    with dep.as_stranger():
        with dep.vm.expect_revert("EXPECTED: caller is not authorized"):
            dep.contract.request_seller_response(case_id)

    with dep.as_owner():
        dep.contract.request_seller_response(case_id)
    assert dep.contract.get_case_status(case_id) == "AWAITING_SELLER"


def test_permissionless_methods_accept_any_caller(deployed):
    dep = deployed
    policy_id = dep.register_policy()
    order_id = dep.record_order(policy_id)
    case_id = dep.open_case(order_id)

    # evaluation, window closing and finalization are permissionless so that
    # nobody can stall a case by refusing to act.
    dep.mock_llm(LLM_PROMPT_PATTERN, llm_reply(verdict="NOT_ELIGIBLE"))
    with dep.as_stranger():
        dep.contract.evaluate_case(case_id)
    assert dep.contract.get_case_status(case_id) == "EVALUATED"

    dep.warp("2026-01-20T00:00:00Z")
    with dep.as_stranger():
        dep.contract.finalize_case(case_id)
    assert dep.contract.get_case_status(case_id) == "FINALIZED"


def test_escalation_requires_the_escalation_role(deployed):
    dep = deployed
    policy_id = dep.register_policy()
    order_id = dep.record_order(policy_id)
    case_id = dep.open_case(order_id)

    for actor in ("buyer", "merchant", "stranger"):
        with getattr(dep, "as_%s" % actor)():
            with dep.vm.expect_revert("EXPECTED: caller is not authorized"):
                dep.contract.escalate_case(case_id, "please look at this")
