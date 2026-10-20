# Equivalence Design — ReturnRight

Every non-deterministic call in ReturnRight uses **custom leader and validator logic**, not `strict_eq`.

| Situation | Strategy |
|---|---|
| Exactly reproducible normalized output | `strict_eq` |
| LLM interpretation, changing web pages, fuzzy judgments | Custom leader and validator functions |

All ReturnRight non-deterministic calls fall in the second row.

## The prompt boundary (P0: injection)

The prompt is XML-like, so an untrusted value that contains a closing tag would break the data
boundary and could be read as an instruction. **Every untrusted value is escaped** before it is
interpolated: the policy title, the clause text, the claim, the evidence reference, the challenge
reason, the page signals and the ids. `<` `>` `&` `"` `'` become entities, control characters are
dropped.

Telling the model to ignore embedded instructions is only the second layer; the escaping is the
boundary. The prompt also states the rule and shows the enforced terms of the policy separately
from the prose of the clauses, so a clause text can never be mistaken for a machine enforced term.

## The content derived evidence id (why it exists)

The stored evidence id (`EV-0`, `EV-1`, ...) is assigned in **submission order**. Rendering that
id in the prompt would leak the submission order into the model input, and the symmetry guarantee
("a permutation of the evidence produces a byte identical prompt") would be false.

So the prompt uses a **content derived id**: `E1`, `E2`, ... assigned by the canonical position of
the evidence. The canonical order is a pure function of the evidence multiset:

1. the two sides are sorted by a content digest, the smaller one becomes side `A`,
2. inside a side the items are sorted by `(kind, ref)`,
3. the ids are assigned in that order.

The contract maps the cited ids back onto the stored records after consensus, so the assessment
still points at the stored evidence. Two items with identical content are interchangeable, which
is the only case where the mapping can pick either one.

The mapping happens on a **copy** of the payload: the object the validators compared must not be
changed after the consensus.

## Call A: interpret_policy (core)

```
PURPOSE: decide eligibility for undecided INTERPRETIVE clauses given two-sided evidence
INPUTS: clause texts, deterministic results, page signals, normalized evidence digest
SOURCE: LLM
LEADER PRODUCES: {verdict, confidence_band, fee_bps, cited_clause_ids, cited_evidence_ids}
VALIDATOR CHECKS: independently derives its own result from the same inputs
EQUIVALENCE RULE:
  - verdict enum must MATCH exactly
  - confidence_band may differ by at most one step
  - fee_bps must be equal, or both within the same coarse fee bucket
  - cited ids are NOT compared: they are explanatory, not part of the decision
  - every cited id must exist in the offered set
  - an ELIGIBLE verdict of the model must cite at least one clause and one evidence id
  - the verdict must be consistent with the deterministic results (no ELIGIBLE after hard FAIL,
    INCONCLUSIVE when the required proof is missing)
  - reasoning_digest is NOT compared
NORMALIZATION: lowercase enums, trim whitespace, dedupe and sort cited ids
FAILURES: invalid JSON, missing keys, unknown enum, hallucinated id, fee out of bounds
FAILURE BEHAVIOR: LLM_ERROR; no assessment appended; case status unchanged
WHY NOT strict_eq: wording, confidence, and partial-fee judgments vary between runs
```

### Citations: explanatory, but not free

The citations are not part of the equivalence comparison: two validators may weigh the same
evidence differently and still agree on the verdict. They are nevertheless part of the integrity of
the assessment:

* every cited id must be one of the offered ids (a hallucinated id is an `LLM_ERROR`),
* the cited ids are mapped back onto the stored records consistently,
* an eligible verdict of the model has to cite at least one clause and one evidence id, because a
  verdict that rests on nothing is an unsupported claim. A model that wants to approve a return
  has to show what it based that on.

## Call B: extract_evidence_facts (web)

```
PURPOSE: pull a small fixed set of TEXT SIGNALS from linked evidence
EXAMPLES: tracking page "delivery_signal: delivered_word|transit_word|unknown" and
          "delivery_date_near_signal: YYYY-MM-DD|unknown"; listing page
          "page_kind_signal: product_words|other_words"; photo host "reachable: yes|no"
LEADER PRODUCES: {signal_name: normalized_value} for a fixed signal list
VALIDATOR CHECKS: independently fetches and extracts the same signal list
EQUIVALENCE RULE: every signal must match exactly; the content fingerprint is recorded but
                   NOT compared (a page may legitimately change between the two fetches)
NORMALIZATION: strip page chrome, timestamps, counters; lowercase; fixed precision
FAILURES: unreachable, changed layout, paywall, empty body
FAILURE BEHAVIOR: the source is marked unreachable, the assessment gets the flag
                   EVIDENCE_UNAVAILABLE and the verdict may become INCONCLUSIVE
```

**The signals are signals, not facts.** The contract cannot authenticate a carrier or a merchant
page, so every signal carries `source_trust="UNVERIFIED"` and the assessment gets the flag
`EVIDENCE_UNVERIFIED`. The prompt tells the model that a signal is what the page says, never proof
that the claim is true and never proof that the page belongs to the order.

**The signals are weak on purpose.** The delivery date is only reported when it stands close to a
delivery word, and the listing classification is only a hint. A date that belongs to something else
on the page is reported as `unknown`.

**The fingerprint.** `content_digest` is a short SHA-256 of the *normalized* page (lower case, all
digits masked, whitespace collapsed). Masking the digits keeps the fingerprint stable against
counters, prices and timestamps. It is stored in the prompt and in the assessment for the audit
trail, and it is excluded from the comparison (`RECORD_ONLY_FACT_KEYS`).

Images: only use image inputs if the verified GenLayer API supports them. Otherwise treat
photo URLs as references whose reachability is checked, and describe the limit in the
threat model. Never claim photo verification you cannot perform.

## Call C: re_evaluate_after_challenge

```
PURPOSE: re-assess with challenge reasons and new evidence
EQUIVALENCE RULE: same as Call A, plus the result must be consistent with the new
                  deterministic results and may not ignore newly submitted evidence ids
FAILURE BEHAVIOR: same as Call A; challenge stays pending; window not double-consumed
```

## Consensus failure is not a verdict

If the leader and the validators do not agree, the non-deterministic block fails. The contract
turns that into a `TRANSIENT` error, the case keeps its status and **no assessment is appended**.
A disagreement is therefore never observable as an INCONCLUSIVE verdict; the two are different
things.

A classified contract error of the leader (for example `LLM_ERROR: invalid json`) is propagated
unchanged, because it is the same failure on every node.

## Principles

- Compare the DECISION, not the explanation.
- Reasoning text is stored for humans and excluded from consensus.
- Prefer bounded enums and coarse bands over numeric confidence.
- Validators check invariants (id subsets, fee bounds, consistency, citations), not just "same
  answer".
- A validator that agrees with garbage is a bug. Always include invariant checks.
- Symmetry invariant: permuting the order of buyer and seller evidence must not change the
  prompt, let alone the verdict, and the prompt must be byte identical (tested in
  `tests/direct/test_symmetry_bytes.py`).
