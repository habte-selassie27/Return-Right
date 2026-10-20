# StudioNet Deployment — ReturnRight

## Status: CURRENT

The contract deployed below runs the **current** source of the repository
(0.2.0). `genlayer code` on the address was compared with
`contracts/return_right.py` and the two are identical, so the deployed
contract is exactly the code that was linted and tested.

```
NETWORK        : studionet (GenLayer Studio Network, chain id 61999)
CONTRACT FILE  : contracts/return_right.py
ADDRESS        : 0x0d72fDA52A264a51D1Fe6F9c6fF3a7FA4E719853
DEPLOY TX      : 0x323228c2f3c547e543682f3e0fe52100282e8ffc5d48128cbcad4beb5a57b771
EXPLORER       : https://explorer-studio.genlayer.com/address/0x0d72fDA52A264a51D1Fe6F9c6fF3a7FA4E719853
STUDIO IMPORT  : https://studio.genlayer.com/?import-contract=0x0d72fDA52A264a51D1Fe6F9c6fF3a7FA4E719853
SCHEMA SAVED AT: deployments/return_right.studionet.schema.json
DATE           : 2026-10-20
```

The deployer is the default account of the CLI
(`0x5b3661c576c7001e6d6279c67f3779705d334c89`); it is therefore the owner and
the initial escalation role of the contract.

## Verification of this deployment

```
genlayer code 0x0d72fDA52A264a51D1Fe6F9c6fF3a7FA4E719853
-> identical to contracts/return_right.py (2568 lines, same md5 after the
   trailing blank lines of the CLI output are stripped)

genlayer schema 0x0d72fDA52A264a51D1Fe6F9c6fF3a7FA4E719853
-> 26 methods (17 write, 9 view), saved to
   deployments/return_right.studionet.schema.json

genlayer call 0x0d72fDA52A264a51D1Fe6F9c6fF3a7FA4E719853 get_config
-> { challenge_window_seconds: 172800,
     escalation_role: '0x5b3661c576c7001e6d6279c67f3779705d334c89',
     max_challenge_rounds: 2, max_evidence_per_side: 8,
     owner: '0x5b3661c576c7001e6d6279c67f3779705d334c89',
     seller_response_window_seconds: 259200 }

genlayer call 0x0d72fDA52A264a51D1Fe6F9c6fF3a7FA4E719853 get_policy --args "POL-0"
-> { clauses: [ { clause_id: 'C1', kind: 'INTERPRETIVE', rule: '',
                  text: 'Item must be unused or in like-new condition.',
                  topic: 'CONDITION' } ],
     excluded_categories: [], max_restocking_bps: 2000,
     merchant: '0x671d07696facea4c26a032bbe04b933284e6c23c',
     policy_id: 'POL-0', required_evidence_kinds: [ 'TEXT_STATEMENT' ],
     return_window_seconds: 518400, status: 'ACTIVE',
     title: 'StudioNet check v2', version: 2 }
```

## Transactions on this deployment

| Tx | Method | From | Result |
|---|---|---|---|
| `0x323228c2…b771` | deploy | `0x5B3661C5…d334c89` | FINALIZED, contract created, source identical to the repository |
| `0xd82b4c3f…08dc` | register_policy | `0x671d0769…C23C` | FINALIZED, leader SUCCESS, 5/5 validators agree, returned `POL-0` |
| `0x8b003fac…510e` | set_config | `0x5B3661C5…d334c89` | FINALIZED, rolled back: `EXPECTED: policy not found` |
| `0x74b06227…f2e4` | set_config | `0x671d0769…C23C` | FINALIZED, rolled back: `EXPECTED: caller is not authorized` |
| `0x9167fb99…9610` | set_escalation_role | `0x671d0769…C23C` | FINALIZED, rolled back: `EXPECTED: caller is not authorized` |

The rejected writes are the access control working as documented: only the
owner may change the config or the escalation role, and a refused call reports
the documented `EXPECTED:` prefix instead of a bare traceback.

## Notes

- StudioNet is gasless; 0 GEN is expected and nothing was spent.
- The contract pins the runner `py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6`
  in its header, so the network runs exactly the code that was linted.
- The explorer base url that the CLI still prints is
  `https://genlayer-explorer.vercel.app`; it returned 503 while this was
  written. This deployment is served by the Studio explorer at
  `https://explorer-studio.genlayer.com`.
- `genlayer write ... --args` needs one shell argument per contract argument
  and a quoted string for values with spaces (`'"Standard returns"'`). Passing
  the whole argument list as one quoted string silently sends a single string
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

In order: receipt with stdout/stderr, schema, code, read calls, then reproduce
in a direct test before changing code.

## Superseded deployments

### 0.1.0 — the code before the 0.2.0 changes (the storage schema changed)

```
ADDRESS        : 0x42BE8C04da3D6DC536113115F4D79D90562aBDa7
DEPLOY TX      : 0x41f56dca0604f30a50304af9a043bbfa8d74bc4692eb2d008c0846f8ca232b41
FIRST WRITE TX : 0x1b162e468305b4dad1d3eb4fac3fe01ae49b32d2e1bdab930fc0508b040c0b5e
                  (register_policy)
```

This deployment predates the content derived evidence ids, the closed response
window, the contestable order record, the enforced-clause rule and the new
storage fields, so it is not the code in the repository. It is listed here
only for the record.

### 0.1.0 — the first deployment of the same day

The contract was deployed twice: first without the per-merchant policy cap, then
again after the cap was added, so that the deployed code matched the source in
the repository at that time.

```
ADDRESS        : 0x4734cbe8Cd18F6246effAAC1E8c31835dbfc4303
DEPLOY TX      : 0x865d064fe25dc0cb320709fac17fddcb37c33120001eed9efdce47f0516a32b0
FIRST WRITE TX : 0xb74368ab26cd6c15b9f6ad254bae88b80441d1041918f5261187b70094c36f69
```
