# Testnet Deployment — ReturnRight

Bradbury and Asimov need funded accounts. The faucet is browser based and
cannot be automated - ask the user to claim GEN before deploying here.

## Record (fill every time)

```
NETWORK / CONTRACT FILE / ADDRESS / DEPLOY TX / EXPLORER LINK
SCHEMA SAVED AT / FIRST READ RESULT / FIRST WRITE TX / RECEIPT STATUS / DATE
```

## Status

- **Bradbury:** not deployed yet. Blocked on a funded account
  (https://testnet-faucet.genlayer.foundation/).
- **Asimov:** not deployed yet. Blocked on a funded account.

StudioNet is deployed and recorded in `deployments/studionet.md`.

## Flow

1. Lint clean, direct tests green, integration tests green.
2. `genlayer network set <network>`; deploy with the genlayer CLI.
3. Record the contract address; `genlayer schema <address>` saved here.
4. Read call to verify; write call; `genlayer receipt <txHash> --stdout --stderr`.
5. Locate the tx in the relevant explorer.

The explorer base urls are configured by the CLI itself:

- Bradbury: https://explorer-bradbury.genlayer.com/
- Asimov: https://explorer-asimov.genlayer.com/

## Debugging

In order: receipt with stdout/stderr, schema, code, read calls, then reproduce in
a direct test before changing code.
