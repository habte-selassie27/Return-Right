# Design — ReturnRight

Domain model, state design, roles, limits, and state machine for the ReturnRight GenLayer Intelligent Contract.

## Domain model

### ReturnPolicy (merchant-owned, versioned)
`ReturnPolicy` = `{ policy_id, version, merchant (address), title, return_window_seconds (sized int), excluded_categories (bounded list), required_evidence_kinds (bounded list), max_restocking_bps (sized int, 0 if none), clauses (bounded list of PolicyClause), status: ACTIVE | DEPRECATED }`

`required_evidence_kinds` are the kinds the merchant requires **from the buyer**. Only the buyer's
evidence can satisfy them, otherwise the merchant could satisfy its own proof requirement with its
own evidence.

### PolicyClause
`PolicyClause` = `{ clause_id, text (bounded), kind: DETERMINISTIC | INTERPRETIVE, topic: WINDOW | CONDITION | DEFECT | CATEGORY | PROOF | FEE | OTHER, rule }`

* `kind = DETERMINISTIC` — the code enforces it. The clause must bind to one of the rules the code
  really implements: `RETURN_WINDOW`, `EXCLUDED_CATEGORY`, `REQUIRED_EVIDENCE`. A deterministic
  clause without a supported rule is **rejected at registration** (`EXPECTED: unsupported
  deterministic clause`), so a merchant can never label a clause deterministic and have it silently
  ignored.
* `kind = INTERPRETIVE` — the validators decide it. An interpretive clause may **not** declare a
  rule (`EXPECTED: interpretive clause cannot declare a rule`).
* Duplicate `clause_id`s are rejected (`EXPECTED: duplicate clause id`).
* The `text` of a clause is a **human description**. The machine enforced terms are the structured
  parameters of the policy (window, excluded categories, required kinds, fee cap) and the `rule` of
  the clause. The prompt shows them separately, so a clause text that contradicts the rule cannot
  be mistaken for the enforced term.

INTERPRETIVE examples: "item must be unused or in like-new condition"; "defects caused by misuse
are not covered".

### OrderRecord
`OrderRecord` = `{ order_id, merchant, buyer (address), policy_id, policy_version (pinned at purchase), category_id, price (sized int), delivered_at (ISO-8601), listing_ref }`

Trust assumption: the merchant records orders honestly. The buyer may contest the delivery date and
the category with `contest_order_record`, which turns the matching hard check into `CONTESTED`
instead of a silent `FAIL`.

### ReturnCase
`ReturnCase` = `{ case_id, order_id, buyer, merchant, reason (enum), claim_text (bounded), evidence (list of EvidenceItem), status (CaseStatus), assessments (append-only list of Assessment), challenge_count, opened_at, evidence_deadline_at, seller_deadline_at, challenge_deadline_at, closed_at, seller_responded, pending_challenge_reason, escalation_reason, escalated_by, contested_fields }`

### EvidenceItem
`EvidenceItem` = `{ evidence_id, submitted_by, side: BUYER | SELLER, kind: PHOTO_URL | TRACKING_URL | LISTING_URL | ORDER_REF | TEXT_STATEMENT, ref (bounded URL/id/text), submitted_at }`

Evidence is append-only and immutable. `side` is derived from the caller and can never be chosen
by the caller.

### Assessment
`Assessment` = `{ assessment_id, case_id, round, verdict: ELIGIBLE_FULL | ELIGIBLE_PARTIAL | NOT_ELIGIBLE | INCONCLUSIVE, confidence_band: LOW | MEDIUM | HIGH, deterministic_results (list of "CHECK_ID:RESULT"), fee_bps, net_refund_bps, cited_clause_ids, cited_evidence_ids, flags, reasoning_digest, produced_by: EVALUATION | RE_EVALUATION, evidence_count }`

* `fee_bps` is the **restocking fee deducted from the refund**, in basis points of the order price.
  It is never a refund amount.
* `net_refund_bps` is what the buyer would receive if the merchant honoured the assessment
  (10000 for a full refund, 10000 - fee_bps for a partial one, 0 otherwise). Both are
  **informational**: the contract never moves money, and a finalized assessment is not an executed
  refund or an entitlement.
* `flags` may contain: `SELLER_NO_RESPONSE`, `PROOF_REQUIREMENT_UNMET`, `HARD_FAIL`,
  `ORDER_RECORD_CONTESTED`, `EVIDENCE_UNAVAILABLE`, `EVIDENCE_UNVERIFIED`, `DETERMINISTIC_SCOPE`.
* `reasoning_digest` is stored for humans and is NOT compared in consensus.

### CaseStatus
`OPEN -> AWAITING_SELLER -> READY -> EVALUATED -> CHALLENGED -> RE_EVALUATED -> ... -> FINALIZED`; `any non-final -> ESCALATED | WITHDRAWN (buyer, before evaluation)`

## State design rules

- GenLayer storage types only: `TreeMap` for keyed records, `DynArray` for append-only lists, dataclasses with `allow_storage`, sized integers for prices, fees, and counters.
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
| Buyer | Open cases on own orders, submit evidence, contest the order record, challenge, withdraw |
| Escalation role | Escalate to an external process |
| Anyone | Open/close the response window, trigger evaluation, finalization (permissionless liveness) |

Authorization is checked at the top of every restricted method. A merchant may only manage their own policies/orders. Buyer and merchant cannot be the same address on one order (`EXPECTED` error). The contract derives `side` from the caller — callers never choose their own side label.

`request_seller_response` is **permissionless** on purpose: the assessment requires the response
window to be closed, so nobody may stall a case by refusing to invite the seller. Opening the
window cannot shorten it (the seller always gets a full window from the moment of the invitation),
so no side is favoured.

## The exact timeline of a case

| Moment | Value | Meaning |
|---|---|---|
| `opened_at` | the transaction time of `open_case` | the case starts |
| `evidence_deadline_at` | `opened_at + window`, moved to `seller_deadline_at` when the seller is invited | the shared evidence deadline of both sides **and the deadline of the invitation** |
| `seller_deadline_at` | `invitation + window` | the end of the seller's response window |
| `challenge_deadline_at` | `assessment + challenge_window` | the window in which the assessment can be challenged |

* The **evidence phase** ends when the response window is closed, or at the shared deadline,
  whichever comes first. Neither side may add evidence after the other side answered.
* Both sides share **one** absolute deadline, so neither side can gain time by acting: the seller
  always gets a full window, and the buyer is never cut off before the seller answered.
* The **invitation deadline** is the initial evidence deadline. After it passed, the seller can no
  longer be invited and anyone may close the case (`close_response_window` from `OPEN`), which
  records the `SELLER_NO_RESPONSE` flag. A case can therefore never stay `OPEN` forever.
* Inside the challenge window both sides may add the proof of their challenge, with exactly the
  same right and the same cap. **After an assessment but before a challenge there is no evidence
  phase any more**: evidence that no challenge would weigh is refused.
* A case may only be assessed (`evaluate_case`) once the response window is closed. Nobody is
  judged before the other side had the chance to answer.

## State machine

| From | Action | To | Who |
|---|---|---|---|
| (none) | open_case | OPEN | buyer of the order |
| OPEN | submit_evidence (buyer) | OPEN | buyer |
| OPEN | contest_order_record | OPEN | buyer |
| OPEN | request_seller_response | AWAITING_SELLER | anyone (before the invitation deadline) |
| OPEN | close_response_window | READY | anyone, after the invitation deadline |
| AWAITING_SELLER | submit_evidence (buyer or seller) | AWAITING_SELLER | the parties |
| AWAITING_SELLER | contest_order_record | AWAITING_SELLER | buyer |
| AWAITING_SELLER | close_response_window | READY | merchant (early) or anyone (after the deadline) |
| READY | evaluate_case | EVALUATED | anyone |
| EVALUATED | challenge_assessment | CHALLENGED | buyer or merchant |
| CHALLENGED | submit_evidence (both sides) | CHALLENGED | the parties, inside the challenge window |
| CHALLENGED | re_evaluate | RE_EVALUATED | anyone |
| RE_EVALUATED | challenge_assessment | CHALLENGED | buyer or merchant (rounds left) |
| EVALUATED / RE_EVALUATED | finalize_case | FINALIZED | anyone after the challenge window |
| any non-final | escalate_case | ESCALATED | escalation role |
| OPEN / AWAITING_SELLER | withdraw_case | WITHDRAWN | buyer |

Rules:
- Any transition not in this table fails with an `EXPECTED` error.
- FINALIZED, ESCALATED, WITHDRAWN are terminal.
- A seller who never responds does **not** auto-lose: the window closes, the flag
  SELLER_NO_RESPONSE is recorded, and evaluation proceeds on available evidence.
- Both sides get the same challenge rights, the same windows and the same evidence cap.

## Deterministic vs non-deterministic split

| Question | Decided by |
|---|---|
| Is the request inside the return window? | Code (`RETURN_WINDOW`) |
| Is the product category excluded by the policy? | Code (`EXCLUDED_CATEGORY`) |
| Are the required evidence kinds present in the buyer's evidence? | Code (`REQUIRED_EVIDENCE`) |
| Is the required proof also available (a link that can be reached)? | Code + the page signals (`REQUIRED_EVIDENCE_AVAILABLE`) |
| Is the requested fee within the policy's max restocking bps? | Code (invariant) |
| Did the seller respond inside the window? | Code (flag only) |
| Is the caller the buyer or merchant on the order? | Code |
| Is the item "like-new" per the clause and the photos/description? | Validators via LLM |
| Is the defect plausibly caused by misuse versus manufacturing? | Validators via LLM |
| Does the listing match what the buyer claims was promised? | Validators via web + LLM |
| Do conflicting buyer and seller statements change the verdict? | Validators via LLM |
| Is the merchant recorded delivery date or category right? | Validators, when the buyer contests it |

Rules:
1. Run all deterministic checks FIRST and record every result, plus one record per deterministic
   clause (`CLAUSE:<id>:<rule>:<result>`), so the assessment shows exactly what was enforced.
2. A failed HARD check (`RETURN_WINDOW`, `EXCLUDED_CATEGORY`) forces NOT_ELIGIBLE. The LLM cannot
   overturn it and is never called.
3. A **contested** hard check is not a failure. The check becomes `CONTESTED`, the flag
   `ORDER_RECORD_CONTESTED` is recorded and the validators decide on the evidence.
4. If all clauses are DETERMINISTIC, the verdict comes from code only. Such an assessment
   establishes **only** what the enforced rules can establish (the window, the category, the
   presence and the availability of the proof); it does not establish that the claim itself is
   true. The flag `DETERMINISTIC_SCOPE` and the reasoning digest say so.
5. Call the LLM only for INTERPRETIVE clauses that remain undecided.
6. ELIGIBLE_PARTIAL must carry a fee_bps between 0 and the policy max. Code validates it.
7. The LLM output is a constrained verdict, never a free-form decision.
8. A missing required proof is **not** a rejection: the case cannot be decided on the merits, so
   the verdict is INCONCLUSIVE with the flag `PROOF_REQUIREMENT_UNMET`. Missing documentation is
   never treated as proof that the return is invalid.

## The proof requirement: PRESENT, AVAILABLE, UNVERIFIED

A required kind of evidence is only satisfied when it is not just **PRESENT** but also
**AVAILABLE**:

| State | Meaning | Satisfies the requirement? |
|---|---|---|
| PRESENT | the buyer submitted an item of the required kind | no |
| AVAILABLE | the item could be reached (a link that answers) or is a plain statement | yes |
| UNVERIFIED | the item is present but could not be reached | no |

Both states are recorded: `REQUIRED_EVIDENCE:PASS|FAIL` (presence) and
`REQUIRED_EVIDENCE_AVAILABLE:PASS|FAIL` (availability). A policy that requires a photo is not
satisfied by a photo URL that returns nothing.

## The contestation rule

The buyer may contest two merchant recorded fields: `DELIVERY_DATE` and `CATEGORY`. They are the
fields that decide a hard check. The buyer's own claim is never merchant recorded, so it is always
left to the validators.

**A contested hard check disables EVERY hard rejection of the case.** The merchant recorded the
whole order, so a dispute about one field puts the reliability of the record in question: the
contract must not reject the case on a field the buyer already disputed, and it must not reject
it on the other field either. The validators decide the whole case on the evidence, and the
assessment records `ORDER_RECORD_CONTESTED`.

If the policy has no interpretive clause, a contested case stays `INCONCLUSIVE` (the code cannot
decide a contested field and there is nothing to weigh).

## Limits and bounds

| Item | Bound |
|---|---|
| clause text | 500 characters |
| claim text | 1000 characters |
| challenge reason | 20 - 500 characters |
| reasoning_digest | 280 characters |
| clauses per policy | 12 |
| excluded categories per policy | 8 |
| required evidence kinds per policy | 8 |
| evidence items per side per case | 8 (configurable, same for both sides) |
| URL length | 512 characters |
| policy versions per policy | 8 |
| policies per merchant | 64 |
| challenge rounds | 2 (configurable, max 10) |
| seller response window / challenge window | config values, same for both sides |

Over-limit input is rejected with `EXPECTED` errors. Never loop unboundedly over storage.

## Error taxonomy

| Prefix | Meaning | ReturnRight examples |
|---|---|---|
| EXPECTED | Caller or logic error | not authorized, invalid transition, window closed, buyer equals merchant, unsupported deterministic clause, invalid evidence reference, invitation window closed |
| EXTERNAL | External source failed | evidence URL unreachable (recorded as a flag, not raised) |
| TRANSIENT | Retryable | upstream timeout, rate limit, **validators did not reach agreement** |
| LLM_ERROR | Model output unusable | invalid JSON, unknown verdict, fee out of bounds, hallucinated id, verdict inconsistent with the deterministic checks |

A consensus failure is a `TRANSIENT` error, never an INCONCLUSIVE verdict: the two are different
things and must not be confused. The case keeps its status and no assessment is appended.
