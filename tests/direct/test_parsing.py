"""Defensive parsing of the model reply (AGENTS.md s16.2)."""

import json

import pytest

from tests.conftest import llm_reply

CLAUSES = ["C1", "C2"]
EVIDENCE = ["E1", "E2"]
MAX_FEE = 1500


def _parse(module, raw, max_fee=MAX_FEE):
    return module.parse_llm_payload(raw, CLAUSES, EVIDENCE, max_fee)


def test_valid_json_is_parsed(contract_module):
    payload = _parse(contract_module, llm_reply(verdict="ELIGIBLE_PARTIAL", fee_bps=500))
    assert payload["verdict"] == "ELIGIBLE_PARTIAL"
    assert payload["confidence_band"] == "MEDIUM"
    assert payload["fee_bps"] == 500
    assert payload["cited_clause_ids"] == ["C1"]
    # An eligible verdict cites the evidence it rests on.
    assert payload["cited_evidence_ids"] == ["E1"]


def test_json_in_a_markdown_fence_is_parsed(contract_module):
    raw = "Here is my answer:\n```json\n" + llm_reply() + "\n```\nThanks!"
    payload = _parse(contract_module, raw)
    assert payload["verdict"] == "ELIGIBLE_FULL"


def test_json_with_commentary_is_parsed(contract_module):
    raw = "Thinking about the claim...\n" + llm_reply() + "\nI hope that helps."
    payload = _parse(contract_module, raw)
    assert payload["verdict"] == "ELIGIBLE_FULL"


def test_enum_casing_is_normalized(contract_module):
    raw = json.dumps(
        {
            "verdict": "eligible_full",
            "confidence_band": "medium",
            "fee_bps": 0,
            "cited_clause_ids": ["C1"],
            "cited_evidence_ids": [],
            "reasoning_digest": "ok",
        }
    )
    payload = _parse(contract_module, raw)
    assert payload["verdict"] == "ELIGIBLE_FULL"
    assert payload["confidence_band"] == "MEDIUM"


def test_documented_aliases_are_accepted(contract_module):
    raw = json.dumps(
        {
            "decision": "NOT_ELIGIBLE",
            "confidence": "LOW",
            "fee": 0,
            "clauses": ["C1"],
            "evidence": ["E1"],
            "rationale": "nothing proves the claim",
        }
    )
    payload = _parse(contract_module, raw)
    assert payload["verdict"] == "NOT_ELIGIBLE"
    assert payload["confidence_band"] == "LOW"
    assert payload["cited_clause_ids"] == ["C1"]
    assert payload["cited_evidence_ids"] == ["E1"]
    assert payload["reasoning_digest"] == "nothing proves the claim"


def test_malformed_json_is_an_llm_error(contract_module):
    with pytest.raises(Exception) as excinfo:
        _parse(contract_module, "{not json at all")
    assert "LLM_ERROR: invalid json" in str(excinfo.value)


def test_empty_reply_is_rejected(contract_module):
    with pytest.raises(Exception) as excinfo:
        _parse(contract_module, "   ")
    assert "LLM_ERROR: empty response" in str(excinfo.value)


def test_a_non_object_payload_is_rejected(contract_module):
    # The reply must be a JSON object; a bare array carries no verdict at all.
    with pytest.raises(Exception) as excinfo:
        _parse(contract_module, "[1, 2, 3]")
    assert "LLM_ERROR: invalid json" in str(excinfo.value)


def test_missing_keys_are_rejected(contract_module):
    raw = json.dumps({"verdict": "ELIGIBLE_FULL", "confidence_band": "MEDIUM"})
    with pytest.raises(Exception) as excinfo:
        _parse(contract_module, raw)
    assert "LLM_ERROR: missing key" in str(excinfo.value)


def test_unknown_verdict_is_rejected(contract_module):
    raw = llm_reply(verdict="MAYBE")
    with pytest.raises(Exception) as excinfo:
        _parse(contract_module, raw)
    assert "LLM_ERROR: unknown enum value" in str(excinfo.value)


def test_unknown_confidence_band_is_rejected(contract_module):
    raw = llm_reply(confidence="VERY_HIGH")
    with pytest.raises(Exception) as excinfo:
        _parse(contract_module, raw)
    assert "LLM_ERROR: unknown enum value" in str(excinfo.value)


def test_wrong_types_are_rejected(contract_module):
    raw = json.dumps(
        {
            "verdict": "ELIGIBLE_FULL",
            "confidence_band": "MEDIUM",
            "fee_bps": "1500",
            "cited_clause_ids": [],
            "cited_evidence_ids": [],
            "reasoning_digest": "x",
        }
    )
    with pytest.raises(Exception) as excinfo:
        _parse(contract_module, raw)
    assert "LLM_ERROR: invalid fee value" in str(excinfo.value)


def test_hallucinated_clause_id_is_rejected(contract_module):
    raw = llm_reply(clauses=["C99"])
    with pytest.raises(Exception) as excinfo:
        _parse(contract_module, raw)
    assert "LLM_ERROR: hallucinated clause id" in str(excinfo.value)


def test_hallucinated_evidence_id_is_rejected(contract_module):
    raw = llm_reply(evidence=["EV-42"])
    with pytest.raises(Exception) as excinfo:
        _parse(contract_module, raw)
    assert "LLM_ERROR: hallucinated evidence id" in str(excinfo.value)


def test_fee_above_the_policy_max_is_rejected(contract_module):
    raw = llm_reply(verdict="ELIGIBLE_PARTIAL", fee_bps=1501)
    with pytest.raises(Exception) as excinfo:
        _parse(contract_module, raw)
    assert "LLM_ERROR: fee outside policy bounds" in str(excinfo.value)


def test_negative_fee_is_rejected(contract_module):
    raw = llm_reply(verdict="ELIGIBLE_PARTIAL", fee_bps=-1)
    with pytest.raises(Exception) as excinfo:
        _parse(contract_module, raw)
    assert "LLM_ERROR: fee outside policy bounds" in str(excinfo.value)


def test_fee_with_a_non_partial_verdict_is_rejected(contract_module):
    raw = llm_reply(verdict="ELIGIBLE_FULL", fee_bps=100)
    with pytest.raises(Exception) as excinfo:
        _parse(contract_module, raw)
    assert "LLM_ERROR: fee not allowed for verdict" in str(excinfo.value)


def test_partial_verdict_requires_a_fee(contract_module):
    raw = llm_reply(verdict="ELIGIBLE_PARTIAL", fee_bps=0)
    with pytest.raises(Exception) as excinfo:
        _parse(contract_module, raw)
    assert "LLM_ERROR: partial verdict requires a fee" in str(excinfo.value)


def test_reasoning_is_truncated_to_the_documented_bound(contract_module):
    raw = llm_reply(reasoning="x" * 500)
    payload = _parse(contract_module, raw)
    assert len(payload["reasoning_digest"]) == 280


def test_cited_ids_are_deduplicated_and_sorted(contract_module):
    raw = llm_reply(clauses=["C2", "C1", "C2"])
    payload = _parse(contract_module, raw)
    assert payload["cited_clause_ids"] == ["C1", "C2"]
