# Equivalence Design — ReturnRight

Every non-deterministic call in ReturnRight uses **custom leader and validator logic**, not `strict_eq`.

| Situation | Strategy |
|---|---|
| Exactly reproducible normalized output | `strict_eq` |
| LLM interpretation, changing web pages, fuzzy judgments | Custom leader and validator functions |

All ReturnRight non-deterministic calls fall in the second row.

## Call A: interpret_policy (core)

```
PURPOSE: decide eligibility for undecided INTERPRETIVE clauses given two-sided evidence
INPUTS: clause texts, deterministic results, normalized evidence digest
SOURCE: LLM
LEADER PRODUCES: {verdict, confidence_band, fee_bps, cited_clause_ids, cited_evidence_ids}
VALIDATOR CHECKS: independently derives its own result from the same inputs
EQUIVALENCE RULE:
  - verdict enum must MATCH exactly
  - confidence_band may differ by at most one step
  - fee_bps must be equal, or both within the same coarse fee bucket
  - cited ids must be subsets of the provided ids
  - verdict must be consistent with deterministic results (no ELIGIBLE after hard FAIL)
  - reasoning_digest is NOT compared
NORMALIZATION: lowercase enums, trim whitespace, dedupe and sort cited ids
FAILURES: invalid JSON, missing keys, unknown enum, hallucinated id, fee out of bounds
FAILURE BEHAVIOR: LLM_ERROR; no assessment appended; case status unchanged
WHY NOT strict_eq: wording, confidence, and partial-fee judgments vary between runs
```

## Call B: extract_evidence_facts (web)

```
PURPOSE: pull a small fixed fact set from linked evidence
EXAMPLES: tracking page "delivered: yes/no" and delivery date bucket; listing page
          "claims waterproof: yes/no"; photo host "image reachable: yes/no"
LEADER PRODUCES: {fact_name: normalized_value} for a fixed fact list
VALIDATOR CHECKS: independently fetches and extracts the same fact list
EQUIVALENCE RULE: booleans/enums match; dates compared at a coarse bucket (for example day)
NORMALIZATION: strip page chrome, timestamps, counters; lowercase; fixed precision
FAILURES: unreachable, changed layout, paywall, empty body
FAILURE BEHAVIOR: EXTERNAL; evidence flagged UNAVAILABLE; verdict may become INCONCLUSIVE
```

Images: only use image inputs if the verified GenLayer API supports them. Otherwise treat photo URLs as references whose reachability is checked, and describe the limit in the threat model.

## Call C: re_evaluate_after_challenge

```
PURPOSE: re-assess with challenge reasons and new evidence
EQUIVALENCE RULE: same as Call A, plus the result must be consistent with the new
                  deterministic results and may not ignore newly submitted evidence ids
FAILURE BEHAVIOR: same as Call A; challenge stays pending; window not double-consumed
```

## Principles

- Compare the **DECISION**, not the explanation.
- Reasoning text is stored for humans and excluded from consensus.
- Prefer bounded enums and coarse bands over numeric confidence.
- Validators check invariants (id subsets, fee bounds, consistency), not just "same answer".
- A validator that agrees with garbage is a bug — always include invariant checks.
- Symmetry invariant: permuting the order of buyer and seller evidence must not change the verdict (tested in `tests/direct/test_symmetry.py` and integration tests).
