"""Consensus behaviour of the two non-deterministic calls.

The model is replaced by a deterministic stand-in (see tests/integration/localnet.py)
because this environment has no LLM API key. Everything else is real: the
leader and the validators execute the contract's own leader/validator functions,
the equivalence rules of docs/equivalence.md are applied to the results and the
leader rotates on disagreement.
"""

from tests.integration.helpers import (
    call_result,
    failure_message,
    open_case,
    read,
    ready_case,
    record_order,
    register_policy,
    votes,
    write,
)


def _case(client, contract, accounts, claim, title):
    """Register a policy, record an order and open a case."""
    merchant = accounts["merchant"]
    buyer = accounts["buyer"]
    policy_id = register_policy(client, contract, merchant, title=title)
    order_id = record_order(client, contract, merchant, buyer.address, policy_id)
    case_id = open_case(client, contract, buyer, order_id, claim=claim)
    # The case may only be assessed once the seller response window is closed.
    ready_case(client, contract, merchant, buyer, case_id)
    return policy_id, order_id, case_id


def test_leader_and_validators_agree_on_a_clear_eligible_case(client, contract, accounts):
    _, _, case_id = _case(
        client,
        contract,
        accounts,
        claim="The unit arrived defective and does not power on.",
        title="Consensus eligible",
    )

    receipt = write(client, contract, "evaluate_case", accounts["outsider"], [case_id])
    assert receipt["status_name"] == "FINALIZED"
    assert votes(receipt) == {"agree"}

    history = read(client, contract, "get_assessment_history", accounts["buyer"], [case_id])
    assert history[0]["verdict"] == "ELIGIBLE_FULL"


def test_equivalent_but_not_identical_outputs_still_reach_agreement(
    client, contract, accounts
):
    """The stand-in answers MEDIUM for the leader and HIGH for the validator.

    The band differs by one step, which the equivalence rule tolerates, so the
    transaction is still finalized.
    """
    _, _, case_id = _case(
        client,
        contract,
        accounts,
        claim="The unit arrived defective and does not power on.",
        title="Consensus tolerance",
    )

    receipt = write(client, contract, "evaluate_case", accounts["outsider"], [case_id])
    assert receipt["status_name"] == "FINALIZED"
    assert votes(receipt) == {"agree"}

    history = read(client, contract, "get_assessment_history", accounts["buyer"], [case_id])
    # The recorded band is the leader's. The validator saw HIGH and accepted it.
    assert history[0]["confidence_band"] == "MEDIUM"
    assert history[0]["verdict"] == "ELIGIBLE_FULL"


def test_leader_and_validators_agree_on_a_clear_not_eligible_case(
    client, contract, accounts
):
    _, _, case_id = _case(
        client,
        contract,
        accounts,
        claim="The unit is NOT-AS-DESCRIBED compared to the listing.",
        title="Consensus not eligible",
    )

    receipt = write(client, contract, "evaluate_case", accounts["outsider"], [case_id])
    assert receipt["status_name"] == "FINALIZED"
    assert votes(receipt) == {"agree"}

    history = read(client, contract, "get_assessment_history", accounts["buyer"], [case_id])
    assert history[0]["verdict"] == "NOT_ELIGIBLE"


def test_a_bad_leader_output_is_rejected(client, contract, accounts):
    """A fee far above the policy maximum must not become an assessment."""
    _, _, case_id = _case(
        client,
        contract,
        accounts,
        claim="The unit arrived defective. BAD-FEE",
        title="Consensus bad fee",
    )

    receipt = write(client, contract, "evaluate_case", accounts["outsider"], [case_id])
    leader = receipt["consensus_data"]["leader_receipt"][0]
    assert leader["execution_result"] == "ERROR"
    assert "LLM_ERROR: fee outside policy bounds" in failure_message(receipt)

    # Nothing was written: the case is untouched.
    history = read(client, contract, "get_assessment_history", accounts["buyer"], [case_id])
    assert history == []
    assert read(client, contract, "get_case_status", accounts["buyer"], [case_id]) == "READY"


def test_validators_that_disagree_with_the_leader_do_not_finalize(
    client, contract, accounts
):
    """A different verdict is never equivalent, so the evaluation does not complete.

    The simulator reports the disagreement by rotating the leader. The rotation
    re-executes the evaluation, which the contract rejects because the case is
    no longer in a state that may be evaluated. The transaction therefore ends
    with an error instead of a clean finalization - and no second assessment is
    appended to the history.
    """
    _, _, case_id = _case(
        client,
        contract,
        accounts,
        claim="The unit arrived defective. FLIP-VERDICT",
        title="Consensus disagreement",
    )

    receipt = write(client, contract, "evaluate_case", accounts["outsider"], [case_id])
    leader = receipt["consensus_data"]["leader_receipt"][0]
    assert leader["execution_result"] == "ERROR"
    assert "EXPECTED: invalid state transition" in failure_message(receipt)

    history = read(client, contract, "get_assessment_history", accounts["buyer"], [case_id])
    assert len(history) <= 1
