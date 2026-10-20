"""The equivalence rules of the two non-deterministic calls (docs/equivalence.md)."""


def _payload(verdict="ELIGIBLE_FULL", confidence="MEDIUM", fee=0, clauses=None, evidence=None):
    return {
        "verdict": verdict,
        "confidence_band": confidence,
        "fee_bps": fee,
        "cited_clause_ids": ["C1"] if clauses is None else clauses,
        "cited_evidence_ids": [] if evidence is None else evidence,
        "reasoning_digest": "some reasoning",
    }


def test_identical_results_are_equivalent(contract_module):
    left = _payload()
    right = _payload()
    assert contract_module.payloads_equivalent(left, right) is True


def test_confidence_bands_one_step_apart_are_equivalent(contract_module):
    left = _payload(confidence="LOW")
    right = _payload(confidence="MEDIUM")
    assert contract_module.payloads_equivalent(left, right) is True

    left = _payload(confidence="MEDIUM")
    right = _payload(confidence="HIGH")
    assert contract_module.payloads_equivalent(left, right) is True


def test_confidence_bands_two_steps_apart_are_not_equivalent(contract_module):
    left = _payload(confidence="LOW")
    right = _payload(confidence="HIGH")
    assert contract_module.payloads_equivalent(left, right) is False


def test_different_verdicts_are_not_equivalent(contract_module):
    left = _payload(verdict="ELIGIBLE_FULL")
    right = _payload(verdict="NOT_ELIGIBLE")
    assert contract_module.payloads_equivalent(left, right) is False


def test_the_same_coarse_fee_bucket_is_equivalent(contract_module):
    left = _payload(verdict="ELIGIBLE_PARTIAL", fee=100)
    right = _payload(verdict="ELIGIBLE_PARTIAL", fee=200)
    assert contract_module.payloads_equivalent(left, right) is True


def test_a_different_fee_bucket_is_not_equivalent(contract_module):
    left = _payload(verdict="ELIGIBLE_PARTIAL", fee=100)
    right = _payload(verdict="ELIGIBLE_PARTIAL", fee=900)
    assert contract_module.payloads_equivalent(left, right) is False


def test_zero_and_a_small_fee_are_not_equivalent(contract_module):
    left = _payload(fee=0)
    right = _payload(verdict="ELIGIBLE_PARTIAL", fee=100)
    assert contract_module.payloads_equivalent(left, right) is False


def test_reasoning_text_differences_are_ignored(contract_module):
    left = _payload()
    right = _payload()
    right["reasoning_digest"] = "a completely different explanation"
    assert contract_module.payloads_equivalent(left, right) is True


def test_cited_ids_are_not_part_of_the_comparison(contract_module):
    left = _payload(clauses=["C1"], evidence=["EV-0"])
    right = _payload(clauses=["C2"], evidence=["EV-1"])
    assert contract_module.payloads_equivalent(left, right) is True


def test_invariants_reject_cited_ids_outside_the_provided_set(contract_module):
    payload = _payload(clauses=["C99"])
    assert (
        contract_module.payload_invariants_hold(
            payload, ["C1"], [], 1500, True, False, []
        )
        is False
    )


def test_invariants_reject_a_fee_outside_the_policy_bounds(contract_module):
    payload = _payload(verdict="ELIGIBLE_PARTIAL", fee=5000)
    assert (
        contract_module.payload_invariants_hold(
            payload, ["C1"], [], 1500, True, False, []
        )
        is False
    )


def test_invariants_reject_a_result_inconsistent_with_the_hard_checks(contract_module):
    payload = _payload(verdict="ELIGIBLE_FULL")
    assert (
        contract_module.payload_invariants_hold(
            payload, ["C1"], [], 1500, True, True, []
        )
        is False
    )


def test_invariants_reject_a_full_refund_without_the_required_evidence(contract_module):
    payload = _payload(verdict="ELIGIBLE_FULL")
    assert (
        contract_module.payload_invariants_hold(
            payload, ["C1"], [], 1500, False, False, []
        )
        is False
    )


def test_invariants_reject_a_re_evaluation_that_ignores_new_evidence(contract_module):
    payload = _payload(evidence=["EV-0"])
    assert (
        contract_module.payload_invariants_hold(
            payload, ["C1"], ["EV-0", "EV-1"], 1500, True, False, ["EV-1"]
        )
        is False
    )


def test_invariants_accept_a_consistent_payload(contract_module):
    payload = _payload(verdict="ELIGIBLE_PARTIAL", fee=500, evidence=["EV-0"])
    assert (
        contract_module.payload_invariants_hold(
            payload, ["C1"], ["EV-0"], 1500, True, False, []
        )
        is True
    )


def test_fee_buckets_are_coarse(contract_module):
    assert contract_module.fee_bucket(0) == 0
    assert contract_module.fee_bucket(1) == 1
    assert contract_module.fee_bucket(250) == 1
    assert contract_module.fee_bucket(251) == 2
    assert contract_module.fee_bucket(1000) == 3
    assert contract_module.fee_bucket(100000) == len(contract_module.FEE_BUCKETS)


def test_web_facts_must_match_exactly(contract_module):
    leader = {"EV-0": {"reachable": "yes", "delivered": "yes", "delivery_day": "2026-01-05"}}
    same = {"EV-0": {"reachable": "yes", "delivered": "yes", "delivery_day": "2026-01-05"}}
    other_day = {"EV-0": {"reachable": "yes", "delivered": "yes", "delivery_day": "2026-01-06"}}
    other_flag = {"EV-0": {"reachable": "no", "delivered": "yes", "delivery_day": "2026-01-05"}}

    assert contract_module.facts_equivalent(leader, same) is True
    assert contract_module.facts_equivalent(leader, other_day) is False
    assert contract_module.facts_equivalent(leader, other_flag) is False


def test_web_facts_with_a_different_shape_are_not_equivalent(contract_module):
    leader = {"EV-0": {"reachable": "yes"}}
    other = {"EV-1": {"reachable": "yes"}}
    assert contract_module.facts_equivalent(leader, other) is False
