# ReturnRight

A reusable two-sided dispute-adjudication primitive for GenLayer Intelligent Contracts. ReturnRight evaluates a return request against a merchant's published return policy using AI-validator consensus, with appeals and an auditable history.

## What it is

- **Standalone Intelligent Contract** — a primitive any merchant can reuse
- **Policy registry + order records + two-sided evidence + consensus assessment + challenge flow**
- **Advisory by default** — records an assessment. Never moves money.

## What it is NOT

- Not a full app (frontend belongs elsewhere)
- Not a payment/escrow system (refund execution is separate)
- Not a thin LLM wrapper (deterministic checks come first)
- Not a hello-world/demo

## Why GenLayer

Return policies involve natural-language judgment ("like-new", "defect not caused by buyer"). Two parties submit conflicting unstructured evidence. Validators must agree on **meaning**, requiring GenLayer's AI-validator consensus.

## State Machine

```
OPEN -> AWAITING_SELLER -> READY -> EVALUATED -> CHALLENGED -> RE_EVALUATED -> ... -> FINALIZED
any non-final -> ESCALATED | WITHDRAWN (buyer, before evaluation)
```

Both sides have identical rights/windows; seller silence does not auto-lose (`SELLER_NO_RESPONSE` flag). A case can only be assessed **after** the seller response window is closed, so nobody is judged before the other side had the chance to answer.

## Public Methods (read vs write)

**Write methods:** `register_policy`, `update_policy`, `deprecate_policy`, `record_order`, `open_case`, `contest_order_record`, `submit_evidence` (side derived from caller), `request_seller_response`, `close_response_window`, `evaluate_case`, `challenge_assessment`, `re_evaluate`, `finalize_case`, `escalate_case`, `withdraw_case`

**View methods:** `get_policy`, `get_policy_version`, `list_active_policies`, `get_order`, `get_case`, `get_case_status`, `get_evidence`, `get_assessment_history`, `get_config`

## Design highlights

- **Deterministic first** — the return window, the excluded category and the required evidence are decided by code. A failed hard check forces `NOT_ELIGIBLE` and the model is never called.
- **Declared rules are enforced rules** — a `DETERMINISTIC` clause must bind to a rule the code really implements (`RETURN_WINDOW`, `EXCLUDED_CATEGORY`, `REQUIRED_EVIDENCE`); otherwise it is rejected at registration.
- **Contestable order records** — the delivery date and the category are merchant assertions. The buyer may contest them, and a contested check becomes `CONTESTED` instead of a silent `FAIL`.
- **Byte-identical prompts** — the model sees neutral labels (A/B) and content-derived ids (E1, E2, ...) in a canonical order, so permuting the evidence cannot change the input.
- **Honest external data** — extracted web facts are claims marked `UNVERIFIED`, fingerprinted for the audit trail, and the assessment says so.
- **Missing proof is not a rejection** — a missing document yields `INCONCLUSIVE` + `PROOF_REQUIREMENT_UNMET`, never `NOT_ELIGIBLE`.
- **Consensus failure is not a verdict** — a leader/validator disagreement is a `TRANSIENT` error; the case is left untouched.

## Quick Start

1. Install deps: `pip install -r requirements.txt && npm install -g genlayer`
2. Lint: `genvm-lint check contracts/return_right.py --json` (after implementation)
3. Direct tests: `pytest tests/direct/ -v`
4. Integration tests: `gltest tests/integration/ -v -s`
5. Deploy via `genlayer network set <network>` and `genlayer deploy`

See `AGENTS.md` for full rules and workflow and `docs/` for the design, the equivalence rules and
the threat model.

## Deployment

See `deployments/studionet.md` and `deployments/testnet.md`.

## Limitations

- Advisory only — no refunds/transfers
- Photo/image verification limited to reachability if GenVM image APIs are not available
- Merchant-recorded orders are trusted as stated unless the buyer contests them
- External pages cannot be authenticated: extracted facts are unverified claims
- LLM interpretation is non-deterministic but constrained by equivalence rules

## Credits

Structure informed by GenLayer starters (Gym, Intelligent Oracle, PM Kit, Boilerplate). Original design for ReturnRight.
