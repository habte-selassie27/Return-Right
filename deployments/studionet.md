# StudioNet Deployment — ReturnRight

## Record

```
NETWORK        : studionet (GenLayer Studio Network)
CONTRACT FILE  : contracts/return_right.py
ADDRESS        : 0x45634C0723245E3D8524B71f56fa111318489Ce7
IMPORT URL     : https://studio.genlayer.com/?import-contract=0x45634C0723245E3D8524B71f56fa111318489Ce7
EXPLORER       : https://explorer-studio.genlayer.com/address/0x45634C0723245E3D8524B71f56fa111318489Ce7
SCHEMA SAVED AT: deployments/return_right.studionet.schema.json
DATE           : 2026-10-20
```

The deployer of this deployment is the default account of the CLI; it is
therefore the owner and the initial escalation role of the contract.

## Verification of the current deployment

Every public method was executed against this deployment on StudioNet with the
real validator consensus. The test parties are two accounts that are **not** the
owner of the deployment, so the owner only methods must refuse them - that
refusal is the expected behaviour and the proof that the access control works.

```
NETWORK / CONTRACT FILE / ADDRESS / DEPLOY TX / EXPLORER LINK
SCHEMA SAVED AT / FIRST READ RESULT / FIRST WRITE TX / RECEIPT STATUS / DATE
```

| Method | Kind | Result on StudioNet |
|---|---|---|
| `get_config` | read | OK - `owner 0x5b3661c5...`, windows 259200 / 172800 |
| `get_policy` | read | OK - the stored clause, rule and terms |
| `get_policy_version` | read | OK - version 1 is still readable after the update |
| `list_active_policies` | read | OK - the policies of the merchant |
| `get_order` | read | OK - buyer, policy version, category, delivery date |
| `get_case` | read | OK - status, deadlines, contested fields, counters |
| `get_case_status` | read | OK - `OPEN` |
| `get_evidence` | read | OK - both items with the derived side |
| `get_assessment_history` | read | OK - two append-only assessments |
| `set_config` | write | REFUSED - `EXPECTED: caller is not authorized` (owner only) |
| `set_escalation_role` | write | REFUSED - `EXPECTED: caller is not authorized` (owner only) |
| `register_policy` | write | OK - `POL-5` |
| `update_policy` | write | OK - version 2 |
| `deprecate_policy` | write | OK - status `DEPRECATED` |
| `record_order` | write | OK - `ORD-0` |
| `open_case` | write | OK - `CAS-0` |
| `submit_evidence` | write | OK - `EV-0` (buyer), `EV-1` (seller) |
| `contest_order_record` | write | OK - the delivery date is `CONTESTED` |
| `request_seller_response` | write | OK - the window opened |
| `close_response_window` | write | OK - the case became `READY` |
| `evaluate_case` | write | OK - the validators agreed on `INCONCLUSIVE` |
| `challenge_assessment` | write | OK - the case became `CHALLENGED` |
| `re_evaluate` | write | OK - a second assessment was appended |
| `finalize_case` | write | REFUSED - `EXPECTED: challenge window is still open` |
| `escalate_case` | write | REFUSED - `EXPECTED: caller is not authorized` (role only) |
| `withdraw_case` | write | OK - the case became `WITHDRAWN` |

The real assessment that the validators produced on the contested case:

```
deterministic_results : RETURN_WINDOW:CONTESTED, EXCLUDED_CATEGORY:PASS,
                         REQUIRED_EVIDENCE:PASS, REQUIRED_EVIDENCE_AVAILABLE:PASS
flags                 : ORDER_RECORD_CONTESTED
verdict               : INCONCLUSIVE (round 1 and round 2)
cited_evidence_ids    : EV-0, EV-1  (the content derived ids mapped back)
reasoning_digest      : "Return window cannot be decided because delivery date
                         is contested and no evidence resolves it. ..."
```

### Known limitation of this deployment

`record_order` takes the buyer as a `str` and the deployed `_to_address` only
accepts a hex string. The GenLayer CLI sends a native address object for an
`address` argument, so the CLI cannot call `record_order` on this deployment
(`EXPECTED: invalid address`). A client that sends the buyer as a string
(the SDK, or the CLI with a string argument) works - the check above used the
SDK. The source has been fixed (`_to_address` accepts an Address, a hex string
and bytes), so the next deployment accepts the native address as well.

## Flow

1. Lint clean, direct tests green, integration tests green.
2. `genlayer network set studionet`; deploy with the genlayer CLI.
3. Record the contract address; `genlayer schema <address>` saved here.
4. Read call to verify; write call; `genlayer receipt <txHash> --stdout --stderr`.
5. Locate the tx in the relevant explorer.

## Debugging

In order: receipt with stdout/stderr, schema, code, read calls, then reproduce in
a direct test before changing code.

## Earlier deployment of the same day

The contract was deployed twice: first without the per-merchant policy cap, then
again after the cap was added, so that the deployed code matches the source in
the repository.

```
ADDRESS        : 0x4734cbe8Cd18F6246effAAC1E8c31835dbfc4303
DEPLOY TX      : 0x865d064fe25dc0cb320709fac17fddcb37c33120001eed9efdce47f0516a32b0
FIRST WRITE TX : 0xb74368ab26cd6c15b9f6ad254bae88b80441d1041918f5261187b70094c36f69
```

## Verification of the current deployment

```
genlayer call 0x42BE8C04da3D6DC536113115F4D79D90562aBDa7 get_policy --args "POL-0"
->
{
  clauses: [ { clause_id: 'C1', kind: 'INTERPRETIVE',
               text: 'Item must be unused or in like-new condition.',
               topic: 'CONDITION' } ],
  excluded_categories: [],
  max_restocking_bps: 1500,
  merchant: '0x5b3661c576c7001e6d6279c67f3779705d334c89',
  policy_id: 'POL-0',
  required_evidence_kinds: [],
  return_window_seconds: 259200,
  status: 'ACTIVE',
  version: 1
}
```

## Notes

- StudioNet is gasless; 0 GEN is expected and nothing was spent.
- The contract pins the runner `py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6`
  in its header, so the network runs exactly the code that was linted.
- `genlayer write ... --args` needs one shell argument per contract argument and
  a quoted string for values with spaces (`'"Standard returns"'`). Passing the
  whole argument list as one quoted string silently sends a single string
  argument, which fails in the contract with a missing-argument TypeError.
- The title of the registered policy contains the extra quotes of the CLI
  string syntax. That is a CLI parsing artefact, not a contract behaviour.

## Flow

1. Lint clean, direct tests green, integration tests green.
2. `genlayer network set studionet`; deploy with the genlayer CLI.
3. Record the contract address; `genlayer schema <address>` saved here.
4. Read call to verify; write call; `genlayer receipt <txHash> --stdout --stderr`.
5. Locate the tx in the relevant explorer.

## Debugging

In order: receipt with stdout/stderr, schema, code, read calls, then reproduce in
a direct test before changing code.
