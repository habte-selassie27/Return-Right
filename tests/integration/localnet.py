"""Start a local GenLayer network for the integration tests.

The network is the lightweight `glsim` simulator shipped with `genlayer-test`. It
needs no Docker and no funded account.

The model provider is replaced by a deterministic stand-in because this
environment has no LLM API key. Everything else is real: the contract runs on the
GenVM standard library, the leader and the validators execute the contract's own
`gl.vm.run_nondet` leader/validator functions, the equivalence rules are applied
to the results and the leader rotates on disagreement.

    python3.12 tests/integration/localnet.py --port 4000

The stand-in is deliberately dumb but rule following: it reads the deterministic
check results out of the prompt and answers accordingly. It also alternates the
confidence band between MEDIUM and HIGH so that the leader and the validators
produce *different but equivalent* outputs - exactly the case the equivalence
rule of docs/equivalence.md has to tolerate.
"""

import argparse
import json
import re
import sys

CHECK_PATTERN = re.compile(r'<check id="([^"]+)" result="([^"]+)"')
CLAUSE_PATTERN = re.compile(r'<clause id="([^"]+)"')
EVIDENCE_PATTERN = re.compile(r'<evidence id="([^"]+)"')
CLAIM_PATTERN = re.compile(r"<claim>\n(.*?)\n</claim>", re.S)

# The stand-in answers this marker with a verdict the model must not produce.
INELIGIBLE_MARKER = "NOT-AS-DESCRIBED"

# The stand-in answers this marker with an illegal fee, so that the rejection of
# a bad leader output can be exercised.
BAD_FEE_MARKER = "BAD-FEE"

# The stand-in answers this marker with a verdict that depends on the call
# counter, so that the validators can be forced to disagree with the leader.
FLIP_MARKER = "FLIP-VERDICT"


def create_deterministic_llm_handler():
    """A rule following stand-in for the model provider.

    The reply depends on how often *this prompt* was seen: the leader sees it
    for the first time, every validator sees it afterwards. That makes the
    leader and the validators differ in a controlled way - one band step, or a
    different verdict - which is exactly what the equivalence rules of
    docs/equivalence.md have to tolerate or reject.
    """
    counters = {}

    def handler(data):
        prompt = data.get("prompt", "")
        checks = dict(CHECK_PATTERN.findall(prompt))
        clause_ids = CLAUSE_PATTERN.findall(prompt)
        evidence_ids = EVIDENCE_PATTERN.findall(prompt)
        claim_match = CLAIM_PATTERN.search(prompt)
        claim = claim_match.group(1) if claim_match else ""

        counters[prompt] = counters.get(prompt, 0) + 1
        turn = counters[prompt]

        if (
            checks.get("RETURN_WINDOW") == "FAIL"
            or checks.get("EXCLUDED_CATEGORY") == "FAIL"
        ):
            verdict = "NOT_ELIGIBLE"
        elif checks.get("REQUIRED_EVIDENCE") == "FAIL":
            verdict = "INCONCLUSIVE"
        elif INELIGIBLE_MARKER in claim:
            verdict = "NOT_ELIGIBLE"
        else:
            verdict = "ELIGIBLE_FULL"

        # Alternate the band so that leader and validators differ by one step.
        band = "MEDIUM" if turn % 2 else "HIGH"

        fee = 0
        if BAD_FEE_MARKER in claim:
            # A fee far above the policy maximum: the validators must reject it.
            fee = 999999

        if FLIP_MARKER in claim:
            # The leader and the validators answer differently, so the
            # validators must reject the leader's verdict.
            verdict = "ELIGIBLE_FULL" if turn % 2 else "NOT_ELIGIBLE"

        payload = {
            "verdict": verdict,
            "confidence_band": band,
            "fee_bps": fee,
            "cited_clause_ids": clause_ids,
            "cited_evidence_ids": evidence_ids,
            "reasoning_digest": "deterministic stand-in for the model provider",
        }
        return {"ok": json.dumps(payload)}

    return handler


def main():
    parser = argparse.ArgumentParser(description="ReturnRight local test network")
    parser.add_argument("--port", type=int, default=4000)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--validators", type=int, default=5)
    parser.add_argument("--max-rotations", type=int, default=3)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    import glsim.live_io as live_io

    live_io.create_llm_handler = lambda provider_config=None: create_deterministic_llm_handler()

    from glsim.server import create_app, run_server

    app = create_app(
        num_validators=args.validators,
        max_rotations=args.max_rotations,
        use_browser=False,
        verbose=args.verbose,
    )

    # The simulator caches the loaded contract class per path. The schema lookup
    # runs the SDK in its own module generation, so a cached class would belong
    # to a stale generation and could not be allocated. Drop the cache before
    # every deploy and let the deploy load the class again.
    engine = app.state.engine
    original_deploy_from_code = engine.deploy_from_code

    def deploy_from_code(code_bytes, calldata_bytes, sender=None):
        engine._class_cache.clear()
        return original_deploy_from_code(code_bytes, calldata_bytes, sender)

    engine.deploy_from_code = deploy_from_code

    print("ReturnRight local network on http://%s:%d/api" % (args.host, args.port))
    sys.stdout.flush()
    run_server(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
