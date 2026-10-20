# Changelog
All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog, and this project adheres to Semantic Versioning.

## [Unreleased]

## 0.3.0 - 2026-10-20
### Added
- StudioNet deployment record for `0x45634C0723245E3D8524B71f56fa111318489Ce7`, including the
  import url, the explorer link, the saved schema and the verification of every public method
  against the live network with the real validator consensus

### Fixed
- `_to_address` accepts a native `Address`, a hex string and bytes. On the GenLayer network a
  native address arrives as an `Address` object, so the deployed contract could not parse the
  buyer of an order that was sent by the CLI (`EXPECTED: invalid address`)

## 0.2.0 - 2026-10-20
### Added
- `contest_order_record`: the buyer may contest the merchant recorded delivery date and
  category; a contested check becomes `CONTESTED` instead of a silent `FAIL`
- `PolicyClause.rule`: a `DETERMINISTIC` clause must bind to a rule the code really enforces
  (`RETURN_WINDOW`, `EXCLUDED_CATEGORY`, `REQUIRED_EVIDENCE`); unsupported ones are rejected
- Per clause enforcement records in the assessment (`CLAUSE:<id>:<rule>:<result>`)
- `net_refund_bps` in the assessment: the restocking fee is a deduction, the net refund is derived
- `EVIDENCE_UNVERIFIED`, `PROOF_REQUIREMENT_UNMET` and `ORDER_RECORD_CONTESTED` assessment flags
- `content_digest` of the inspected page (normalized, digits masked) for the audit trail
- Evidence URL validation: http(s) only, no credentials, no loopback/private/link-local/metadata hosts
- Direct tests for the lifecycle, the contested records and the leader/validator behaviour
  (`test_lifecycle.py`, `test_contested_records.py`, `test_consensus.py`)
- Integration tests for the closed response window, the contested order record and the
  enforced-clause rule

### Changed
- The prompt uses content derived evidence ids (`E1`, `E2`, ...) instead of the stored
  submission-order ids, so a permutation of the evidence produces a byte identical prompt
- A case may only be assessed once the seller response window is closed
- `request_seller_response` is permissionless, so nobody can stall a case
- Both sides share one absolute evidence deadline; the evidence phase ends with the response window
- The required evidence kinds are only satisfied by the **buyer's** evidence
- Missing required proof yields `INCONCLUSIVE` instead of `NOT_ELIGIBLE`
- A consensus failure is reported as `TRANSIENT` and never as an `INCONCLUSIVE` verdict
- Web facts are unverified claims (`source_trust`), and the extracted fact names changed to
  `delivery_claim`, `delivery_day_claim` and `page_kind_claim`
- The StudioNet deployment of 0.1.0 predates these changes; the current code is
  deployed at `0x0d72fDA52A264a51D1Fe6F9c6fF3a7FA4E719853` (deploy tx
  `0x323228c2f3c547e543682f3e0fe52100282e8ffc5d48128cbcad4beb5a57b771`), and the
  deployed source is identical to `contracts/return_right.py`. The old 0.1.0
  deployment `0x42BE8C04da3D6DC536113115F4D79D90562aBDa7` is superseded and
  listed in `deployments/studionet.md`.

## 0.1.0 - 2026-10-20
### Added
- The ReturnRight Intelligent Contract (`contracts/return_right.py`):
  - Merchant owned, versioned return policy registry (`register_policy`,
    `update_policy`, `deprecate_policy`, `list_active_policies`).
  - Orders pinned to the policy version that applied at purchase
    (`record_order`).
  - Return cases with two sided, append-only evidence (`open_case`,
    `submit_evidence`); the side is derived from the caller.
  - A strict state machine: OPEN -> AWAITING_SELLER -> READY -> EVALUATED ->
    CHALLENGED -> RE_EVALUATED -> FINALIZED, plus ESCALATED and WITHDRAWN.
  - Deterministic checks first (return window, excluded category, required
    evidence kinds), with hard failures that never reach the model.
  - Two custom leader/validator non-deterministic blocks: the interpretation of
    the residual INTERPRETIVE clauses (LLM) and the extraction of a small
    structured fact set from linked evidence (web).
  - Defensive parsing of the model reply with the documented error taxonomy
    (EXPECTED / EXTERNAL / TRANSIENT / LLM_ERROR).
  - Symmetric design: identical evidence caps, windows and challenge rights,
    neutral evidence labels and a canonical evidence order.
- Direct tests (112) with mocked web and model calls:
  `tests/direct/test_policies.py`, `test_orders.py`, `test_cases.py`,
  `test_checks.py`, `test_parsing.py`, `test_equivalence_helpers.py`,
  `test_challenges.py`, `test_access_control.py`, `test_symmetry.py`,
  `test_web_facts.py`, `test_security.py`, `test_smoke.py`.
- Integration tests (12) against a live network with real consensus:
  `tests/integration/test_end_to_end.py`, `test_consensus.py`, plus
  `tests/integration/localnet.py`, a lightweight local network with a
  deterministic model stand-in.
- Documentation: `README.md`, `docs/design.md`, `docs/equivalence.md`,
  `docs/threat-model.md`, `docs/examples.md`.
- StudioNet deployment: contract `0x42BE8C04da3D6DC536113115F4D79D90562aBDa7`,
  deploy tx `0x41f56dca0604f30a50304af9a043bbfa8d74bc4692eb2d008c0846f8ca232b41`,
  schema saved in `deployments/return_right.studionet.schema.json`.

## 0.0.1 - 2026-10-20
### Added
- AGENTS.md (ReturnRight GenLayer Intelligent Contract specification)
- Initial project structure (directories per AGENTS.md layout)
- design.md, equivalence.md, threat-model.md, examples.md
- README.md, .gitignore, .env.example, requirements.txt
