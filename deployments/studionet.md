# StudioNet Deployment — ReturnRight

## Record (fill every time)

```
NETWORK / CONTRACT FILE / ADDRESS / DEPLOY TX / EXPLORER LINK
SCHEMA SAVED AT / FIRST READ RESULT / FIRST WRITE TX / RECEIPT STATUS / DATE
```

- StudioNet is gasless; 0 GEN is expected.
- Deploy first on StudioNet before Bradbury/Asimov.
- Use `genlayer network set studionet` (never override RPC manually).

## Flow

1. Lint clean, direct tests green, integration tests green.
2. `genlayer network set studionet`; deploy with the genlayer CLI.
3. Record the contract address; `genlayer schema <address>` saved here.
4. Read call to verify; write call; `genlayer receipt <txHash> --stdout --stderr`.
5. Locate the tx in the relevant explorer.

## Debugging

In order: receipt with stdout/stderr, schema, code, read calls, then reproduce in a direct test before changing code.
