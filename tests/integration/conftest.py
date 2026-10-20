"""Fixtures for the ReturnRight integration tests."""

import pytest
from eth_account import Account
from genlayer_py import create_client
from genlayer_py.types import TransactionStatus

from tests.integration.helpers import CONTRACT_PATH, RPC_URL


@pytest.fixture(scope="module")
def accounts():
    """The parties of a dispute: a merchant, a buyer and an outsider."""
    return {
        "merchant": Account.create(),
        "buyer": Account.create(),
        "outsider": Account.create(),
    }


@pytest.fixture(scope="module")
def client(accounts):
    """A client for the local network."""
    return create_client(endpoint=RPC_URL, account=accounts["merchant"])


@pytest.fixture(scope="module")
def contract(client):
    """Deploy ReturnRight and return its address."""
    tx = client.deploy_contract(code=CONTRACT_PATH.read_text(), args=[])
    receipt = client.wait_for_transaction_receipt(tx, status=TransactionStatus.FINALIZED)
    assert receipt["status_name"] == "FINALIZED"
    return receipt["data"]["contract_address"]
