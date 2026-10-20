"""Shared fixtures for the ReturnRight test suite.

Direct tests (tests/direct) run the contract in-process with mocked web and LLM
calls, so they are fast and deterministic:

    pytest tests/direct/ -v

Integration tests (tests/integration) exercise real consensus:

    gltest tests/integration/ -v -s
"""

import hashlib
import json
import sys
from pathlib import Path

import pytest

CONTRACT_PATH = Path(__file__).resolve().parent.parent / "contracts" / "return_right.py"

# The direct loader imports the contract module under this name.
CONTRACT_MODULE_NAME = "_contract_" + CONTRACT_PATH.stem

# The prompt always starts with this sentence, so it is a stable mock key.
LLM_PROMPT_PATTERN = "impartial adjudicator"

# A clause that the code really enforces. A DETERMINISTIC clause must bind to
# one of the rules the contract implements.
DETERMINISTIC_CLAUSE = {
    "clause_id": "C1",
    "text": "Returns are accepted when the buyer provides a proof of purchase.",
    "kind": "DETERMINISTIC",
    "topic": "PROOF",
    "rule": "REQUIRED_EVIDENCE",
}

# The transaction time every test starts from. The default delivery timestamp of
# the fixtures is one day earlier, so a fresh case is inside the return window.
DEFAULT_NOW = "2026-01-02T00:00:00Z"


def llm_reply(
    verdict="ELIGIBLE_FULL",
    confidence="MEDIUM",
    fee_bps=0,
    clauses=None,
    evidence=None,
    reasoning="The buyer's evidence satisfies the policy.",
):
    """Build a model reply that satisfies the prompt contract."""
    return json.dumps(
        {
            "verdict": verdict,
            "confidence_band": confidence,
            "fee_bps": fee_bps,
            "cited_clause_ids": ["C1"] if clauses is None else clauses,
            "cited_evidence_ids": [] if evidence is None else evidence,
            "reasoning_digest": reasoning,
        }
    )


def hex_address(seed: str) -> str:
    """Deterministic lowercase hex address for a seed string."""
    return "0x" + hashlib.sha256(seed.encode()).digest()[:20].hex()


class Deployment:
    """A deployed ReturnRight contract plus the helpers the tests need."""

    def __init__(self, contract, module, vm):
        self.contract = contract
        self.module = module
        self.vm = vm

    # -- parties ---------------------------------------------------------
    @property
    def owner(self) -> str:
        return hex_address("owner")

    @property
    def merchant(self) -> str:
        return hex_address("merchant")

    @property
    def buyer(self) -> str:
        return hex_address("buyer")

    @property
    def stranger(self) -> str:
        return hex_address("stranger")

    def as_owner(self):
        return self.vm.prank(_raw(self.owner))

    def as_merchant(self):
        return self.vm.prank(_raw(self.merchant))

    def as_buyer(self):
        return self.vm.prank(_raw(self.buyer))

    def as_stranger(self):
        return self.vm.prank(_raw(self.stranger))

    # -- time ------------------------------------------------------------
    def warp(self, iso: str) -> None:
        """Set the transaction datetime (identical for leader and validators)."""
        self.vm.warp(iso)
        import genlayer.gl as genlayer_gl

        genlayer_gl.message_raw["datetime"] = iso

    def now(self) -> str:
        import genlayer.gl as genlayer_gl

        return genlayer_gl.message_raw["datetime"]

    # -- mocking ---------------------------------------------------------
    def mock_llm(self, pattern: str, response: str) -> None:
        self.vm.mock_llm(pattern, response)

    def mock_web(self, pattern: str, status: int, body: str) -> None:
        self.vm.mock_web(pattern, {"method": "GET", "status": status, "body": body})

    def capture_prompts(self, response: str):
        """Install a live model handler that records every prompt it receives."""
        captured = []
        self.captured_prompts = captured

        def handler(data):
            captured.append(data["prompt"])
            return {"ok": response}

        self.vm._live_llm_handler = handler
        return captured

    # -- consensus --------------------------------------------------------
    def validators(self):
        """The validators captured by the last gl.vm.run_nondet calls."""
        return self.vm._captured_validators

    def run_last_validator(self, leader_result=None):
        """Run the validator of the most recent non-deterministic block."""
        if leader_result is None:
            return self.vm.run_validator()
        return self.vm.run_validator(leader_result=leader_result)

    def llm_hits(self) -> int:
        """How many LLM mocks were actually called."""
        return len(self.vm._llm_mocks_hit)

    def web_hits(self) -> int:
        """How many web mocks were actually called."""
        return len(self.vm._web_mocks_hit)

    # -- convenience builders ---------------------------------------------
    def register_policy(
        self,
        title="Standard returns",
        window=259200,
        excluded=None,
        required=None,
        max_fee=1500,
        clauses=None,
    ) -> str:
        if excluded is None:
            excluded = []
        if required is None:
            required = ["TEXT_STATEMENT"]
        if clauses is None:
            clauses = [
                {
                    "clause_id": "C1",
                    "text": "Item must be unused or in like-new condition.",
                    "kind": "INTERPRETIVE",
                    "topic": "CONDITION",
                }
            ]
        with self.as_merchant():
            return self.contract.register_policy(
                title, window, excluded, required, max_fee, clauses
            )

    def request_seller_response(self, case_id: str) -> None:
        """Open the seller response window (permissionless in the contract)."""
        with self.as_buyer():
            self.contract.request_seller_response(case_id)

    def close_seller_window(self, case_id: str, by_merchant: bool = True) -> None:
        """Close the seller response window, which makes the case ready."""
        if by_merchant:
            with self.as_merchant():
                self.contract.close_response_window(case_id)
        else:
            with self.as_stranger():
                self.contract.close_response_window(case_id)

    def ready_case(self, case_id: str, seller_evidence=None) -> str:
        """Take a case to READY: the seller window opened and closed.

        A case may only be assessed once the response window is closed, so
        almost every test needs this step.
        """
        self.request_seller_response(case_id)
        if seller_evidence is not None:
            with self.as_merchant():
                self.contract.submit_evidence(
                    case_id, "TEXT_STATEMENT", seller_evidence
                )
        self.close_seller_window(case_id)
        return case_id

    def record_order(
        self,
        policy_id,
        version=1,
        buyer=None,
        category="ELECTRONICS",
        price=10000,
        delivered_at="2026-01-01T00:00:00Z",
        listing_ref="https://shop.example/item/1",
    ) -> str:
        with self.as_merchant():
            return self.contract.record_order(
                policy_id,
                version,
                buyer if buyer is not None else self.buyer,
                category,
                price,
                delivered_at,
                listing_ref,
            )

    def open_case(
        self,
        order_id,
        reason="DEFECTIVE",
        claim="The device arrived defective and does not power on.",
    ) -> str:
        with self.as_buyer():
            return self.contract.open_case(order_id, reason, claim)


def _raw(hex_addr: str) -> bytes:
    return bytes.fromhex(hex_addr[2:])


@pytest.fixture
def deployed(direct_vm, direct_deploy):
    """Deploy ReturnRight and expose the contract, its module and the VM."""
    # The deployer becomes the owner of the contract.
    direct_vm.sender = _raw(hex_address("owner"))
    instance = direct_deploy(str(CONTRACT_PATH))
    module = sys.modules[CONTRACT_MODULE_NAME]
    deployment = Deployment(instance, module, direct_vm)
    # A fixed "now" keeps the return window deterministic across the tests.
    deployment.warp(DEFAULT_NOW)
    return deployment


@pytest.fixture
def contract_module(deployed):
    """The contract module, so that the pure helpers can be unit tested."""
    return deployed.module
