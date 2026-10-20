# StudioNet Deployment — ReturnRight

## Status: OUTDATED

The deployment recorded below was made from the contract **before** the 0.2.0
changes (content derived evidence ids, the closed response window, the
contestable order record, the enforced-clause rule, the new storage fields).
The storage schema changed, so the deployed contract is **not** the code in the
repository and has to be redeployed before it is used again.

```
NETWORK        : studionet (GenLayer Studio Network, chain id 61999)
CONTRACT FILE  : contracts/return_right.py
ADDRESS        : 0x42BE8C04da3D6DC536113115F4D79D90562aBDa7
DEPLOY TX      : 0x41f56dca0604f30a50304af9a043bbfa8d74bc4692eb2d008c0846f8ca232b41
EXPLORER       : https://genlayer-explorer.vercel.app  (base url; the per-tx path
                 format could not be verified because the explorer returned 503
                 while this was written - the hashes above are the reference)
SCHEMA SAVED AT: deployments/return_right.studionet.schema.json
FIRST READ     : get_config -> {challenge_window_seconds: 172800,
                 escalation_role: '0x5b3661c576c7001e6d6279c67f3779705d334c89',
                 max_challenge_rounds: 2, max_evidence_per_side: 8,
                 owner: '0x5b3661c576c7001e6d6279c67f3779705d334c89',
                 seller_response_window_seconds: 259200}
FIRST WRITE TX : 0x1b162e468305b4dad1d3eb4fac3fe01ae49b32d2e1bdab930fc0508b040c0b5e
                 (register_policy)
RECEIPT STATUS : deploy FINALIZED (leader SUCCESS, 5/5 validators AGREE)
                 write ACCEPTED (leader SUCCESS, 5/5 validators SUCCESS)
DATE           : 2026-10-20
```

The deployer of this deployment is the default account of the CLI
(`0x5b3661c576c7001e6d6279c67f3779705d334c89`); it is therefore the owner and
the initial escalation role of the contract.

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
