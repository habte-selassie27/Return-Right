# Design — ReturnRight

Domain model, state design, roles, limits, and state machine for the ReturnRight GenLayer Intelligent Contract.

## Domain model

### ReturnPolicy (merchant-owned, versioned)
`ReturnPolicy` = `{ policy_id, version, merchant (address), title, return_window_units (sized int), excluded_categories (bounded list), required_evidence_kinds (bounded list), max_restocking_bps (sized int, 0 if none), clauses (bounded list of PolicyClause), status: ACTIVE | DEPRECATED }`

### PolicyClause
`PolicyClause` = `{ clause_id, text (bounded), kind: DETERMINISTIC | INTERPRETIVE, topic: WINDOW | CONDITION | DEFECT | CATEGORY | PROOF | FEE | OTHER }`

INTERPRETIVE examples: "item must be unused or in like-new condition"; "defects caused by misuse are not covered".

### OrderRecord
`OrderRecord` = `{ order_id, merchant, buyer (address), policy_id, policy_version (pinned at purchase), category_id, price (sized int), delivered_ref, listing_ref }`

Trust assumption: the merchant records orders honestly; the buyer may contest delivery details with evidence, which can push the verdict to INCONCLUSIVE.

### ReturnCase
`ReturnCase` = `{ case_id, order_id, buyer, merchant, reason (enum), claim_text (bounded), evidence (list of EvidenceItem), status (CaseStatus), assessments (append-only list of Assessment), challenge_count, opened_ref, seller_deadline_ref, closed_ref }`

### EvidenceItem
`EvidenceItem` = `{ evidence_id, submitted_by, side: BUYER | SELLER | NEUTRAL, kind: PHOTO_URL | TRACKING_URL | LISTING_URL | ORDER_REF | TEXT_STATEMENT, ref (bounded URL/id/text), submitted_ref }`

Evidence is append-only and immutable once submitted.

### Assessment
`Assessment` = `{ assessment_id, case_id, round, verdict: ELIGIBLE_FULL | ELIGIBLE_PARTIAL | NOT_ELIGIBLE | INCONCLUSIVE, confidence_band: LOW | MEDIUM | HIGH, deterministic_results (list of (check_id, PASS | FAIL | NOT_APPLICABLE)), fee_bps (sized int, bounded by policy max), cited_clause_ids (bounded list), cited_evidence_ids (bounded list), flags (bounded list: SELLER_NO_RESPONSE, EVIDENCE_UNAVAILABLE, ...), reasoning_digest (bounded text, NOT compared in consensus), produced_by: EVALUATION | RE_EVALUATION }`

### CaseStatus
`OPEN -> AWAITING_SELLER -> READY -> EVALUATED -> CHALLENGED -> RE_EVALUATED -> ... -> FINALIZED`; `any non-final -> ESCALATED | WITHDRAWN (buyer, before evaluation)`

## State design rules

- GenLayer storage types only: `TreeMap` for keyed records, `DynArray` for append-only lists, dataclasses with `allow_storage`, sized integers for prices/fees/counters.
- Assessments and evidence are **append-only**. Never overwrite or delete.
- Policy edits create a new version; orders pin the policy version they were bought under.
- Every list has a documented bound (see Limits below).
- Store references and digests, not documents or raw fetched pages. Never store secrets.
- Use basis points (integers) for fees. Never floats.

## Roles and access control

| Role | Capability |
|---|---|
| Owner | Set config, assign escalation role |
| Merchant | Register/deprecate own policies, record own orders, submit seller evidence, challenge |
| Buyer | Open cases on own orders, submit evidence, challenge, withdraw |
| Escalation role | Escalate to an external process |
| Anyone | Trigger evaluation, window close, finalization (permissionless liveness) |

Authorization is checked at the top of every restricted method. A merchant may only manage their own policies/orders. Buyer and merchant cannot be the same address on one order (`EXPECTED` error). The contract derives `side` from the caller — callers never choose their own side label.

## Limits and bounds

| Item | Bound |
|---|---|
| clause text, claim text, challenge reason | fixed max lengths (TBD values) |
| reasoning_digest | 280 chars |
| clauses per policy | fixed max (TBD) |
| excluded categories per policy | fixed max (TBD) |
| evidence items per side per case | fixed max (TBD) |
| URL length | fixed max (TBD) |
| challenge rounds | fixed max (TBD) |
| seller response window / challenge window | config values, same for both sides (TBD) |
| high-value escalation threshold | config value (TBD) |

Over-limit input is rejected with `EXPECTED` errors. Never loop unboundedly over storage.

## State machine

| From | Action | To | Who |
|---|---|---|---|
| (none) | open_case | OPEN | buyer of the order |
| OPEN | submit_evidence (buyer) | OPEN | buyer |
| OPEN | request_seller_response | AWAITING_SELLER | buyer or anyone (rate bounded) |
| AWAITING_SELLER | submit_evidence (seller) | AWAITING_SELLER | merchant |
| AWAITING_SELLER | close_response_window | READY | anyone after deadline, or merchant |
| OPEN / READY | evaluate_case | EVALUATED | anyone (see rules) |
| EVALUATED | challenge_assessment | CHALLENGED | buyer or merchant (window, rounds) |
| CHALLENGED | re_evaluate | RE_EVALUATED | anyone |
| RE_EVALUATED | challenge_assessment | CHALLENGED | buyer or merchant (rounds left) |
| EVALUATED / RE_EVALUATED | finalize_case | FINALIZED | anyone after window, no challenge |
| any non-final | escalate_case | ESCALATED | escalation role |
| OPEN / AWAITING_SELLER | withdraw_case | WITHDRAWN | buyer |

Rules:
- Any transition not in this table fails with an `EXPECTED` error.
- FINALIZED, ESCALATED, WITHDRAWN are terminal.
- A seller who never responds does **not** auto-lose: the window closes, the flag `SELLER_NO_RESPONSE` is recorded, and evaluation proceeds on available evidence.
- Both sides get the same challenge rights and the same window length.
