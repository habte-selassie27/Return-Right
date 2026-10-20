"""Helpers for the ReturnRight integration tests.

The integration tests run against a live GenLayer network. Start one with:

    python3.12 tests/integration/localnet.py --port 4000

and then run the tests with:

    gltest tests/integration/ -v -s
"""

import datetime
import json
from pathlib import Path

from genlayer_py.types import TransactionStatus

CONTRACT_PATH = (
    Path(__file__).resolve().parent.parent.parent / "contracts" / "return_right.py"
)
RPC_URL = "http://127.0.0.1:4000/api"

# A claim that makes the model stand-in answer NOT_ELIGIBLE.
NOT_ELIGIBLE_CLAIM = "The unit is NOT-AS-DESCRIBED compared to the listing."


def days_ago(days: int = 1) -> str:
    """An ISO-8601 UTC timestamp `days` days in the past.

    The network clock is the real time, so the delivery date of a fixture order
    has to be close to it for the request to be inside the return window.
    """
    moment = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
        days=days
    )
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def write(client, address, method, account, args=None, kwargs=None):
    """Send a write transaction and wait until it is finalized."""
    tx = client.write_contract(
        address=address,
        function_name=method,
        account=account,
        args=args or [],
        kwargs=kwargs or {},
    )
    return client.wait_for_transaction_receipt(tx, status=TransactionStatus.FINALIZED)


def call_result(receipt):
    """The return value of a write transaction."""
    result = receipt["consensus_data"]["leader_receipt"][0]["result"]
    payload = result.get("payload") if isinstance(result, dict) else None
    if isinstance(payload, str):
        # A scalar return value (for example a version number) comes back as
        # its readable text.
        return payload
    readable = payload.get("readable") if isinstance(payload, dict) else None
    if readable is None:
        return None
    try:
        return json.loads(readable)
    except (ValueError, TypeError):
        return readable


def failure_message(receipt):
    """The error message of a failed transaction, if any."""
    leader = receipt["consensus_data"]["leader_receipt"][0]
    stderr = leader.get("genvm_result", {}).get("stderr", "")
    result = leader.get("result")
    if isinstance(result, dict):
        payload = result.get("payload")
        if isinstance(payload, str) and payload:
            return payload
        if isinstance(payload, dict) and payload.get("readable"):
            return payload["readable"]
    return stderr


def votes(receipt):
    """The votes of the validators."""
    return set(receipt["consensus_data"]["votes"].values())


def read(client, address, method, account, args=None):
    """Call a read-only method."""
    return client.read_contract(
        address=address,
        function_name=method,
        account=account,
        args=args or [],
    )


def register_policy(client, address, merchant, **overrides):
    """Register a policy and return its id."""
    title = overrides.get("title", "Standard returns")
    window = overrides.get("window", 259200)
    excluded = overrides.get("excluded", [])
    required = overrides.get("required", [])
    max_fee = overrides.get("max_fee", 1500)
    clauses = overrides.get(
        "clauses",
        [
            {
                "clause_id": "C1",
                "text": "Item must be unused or in like-new condition.",
                "kind": "INTERPRETIVE",
                "topic": "CONDITION",
            }
        ],
    )
    receipt = write(
        client,
        address,
        "register_policy",
        merchant,
        [title, window, excluded, required, max_fee, clauses],
    )
    return call_result(receipt)


def record_order(
    client,
    address,
    merchant,
    buyer,
    policy_id,
    version=1,
    category="ELECTRONICS",
    price=10000,
    delivered_at=days_ago(1),
    listing_ref="https://shop.example/item/1",
):
    """Record an order and return its id."""
    receipt = write(
        client,
        address,
        "record_order",
        merchant,
        [
            policy_id,
            version,
            buyer,
            category,
            price,
            delivered_at,
            listing_ref,
        ],
    )
    return call_result(receipt)


def open_case(
    client,
    address,
    buyer,
    order_id,
    reason="DEFECTIVE",
    claim="The unit arrived defective and does not power on.",
):
    """Open a case and return its id."""
    receipt = write(client, address, "open_case", buyer, [order_id, reason, claim])
    return call_result(receipt)


def ready_case(
    client,
    address,
    merchant,
    buyer,
    case_id,
    seller_claim=None,
    buyer_claim="The unit arrived defective and does not power on.",
):
    """Take a case to READY: the seller window is opened and closed.

    A case may only be assessed once the response window is closed, so every
    evaluation has to go through this step. The buyer submits a statement
    first, because an eligible verdict has to rest on cited evidence.
    """
    if buyer_claim is not None:
        write(
            client,
            address,
            "submit_evidence",
            buyer,
            [case_id, "TEXT_STATEMENT", buyer_claim],
        )
    write(client, address, "request_seller_response", buyer, [case_id])
    if seller_claim is not None:
        write(
            client,
            address,
            "submit_evidence",
            merchant,
            [case_id, "TEXT_STATEMENT", seller_claim],
        )
    write(client, address, "close_response_window", merchant, [case_id])
    return case_id
