"""Tests for the DynamoDB store.

No LocalStack: a fake table records what would be written. The test at the
end talks to LocalStack and skips itself when LocalStack is not running.
"""

import os
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from securepay_apis.exchange_rates import store

_RESULT = {
    "date": "2026-10-02",
    "rates": {
        "USD": Decimal(1),
        "COP": Decimal("3317.65"),
        "EUR": Decimal("0.88286"),
        "JPY": Decimal("157.78"),
    },
    "source": "https://api.frankfurter.dev/v2/rates?base=USD&quotes=COP,EUR,JPY",
}


class _FakeTable:
    """Just enough of a boto3 Table: batch_writer().put_item()."""

    def __init__(self):
        self.items = []

    def batch_writer(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def put_item(self, Item):
        self.items.append(Item)


def test_item_has_the_key_the_rates_and_the_source():
    item = store.to_item(_RESULT)

    assert item["base"] == "USD"
    assert item["rate_date"] == "2026-10-02"
    assert item["rates"] == _RESULT["rates"]
    assert item["source"] == _RESULT["source"]


def test_rates_stay_decimal():
    """boto3 rejects floats when writing to DynamoDB."""
    item = store.to_item(_RESULT)

    assert all(isinstance(rate, Decimal) for rate in item["rates"].values())


def test_expiry_counts_from_the_load_not_from_the_rate_date():
    """A past day loaded today must live 30 days from today."""
    now = datetime(2026, 10, 20, tzinfo=timezone.utc)

    item = store.to_item(_RESULT, now=now)

    assert item["expires_at"] == int(datetime(2026, 11, 19, tzinfo=timezone.utc).timestamp())


def test_save_writes_one_item_per_day():
    table = _FakeTable()
    second_day = {**_RESULT, "date": "2026-10-05"}

    count = store.save([_RESULT, second_day], table=table)

    assert count == 2
    assert [i["rate_date"] for i in table.items] == ["2026-10-02", "2026-10-05"]


def test_table_name_comes_from_the_environment(monkeypatch):
    monkeypatch.setenv("RATES_TABLE", "another-table")

    assert store.table_name() == "another-table"


# --- Against LocalStack -------------------------------------------------------

def _localstack_table():
    """A throwaway table in LocalStack, or skip if LocalStack is not up."""
    boto3 = pytest.importorskip("boto3")
    endpoint = os.getenv("AWS_ENDPOINT_URL")
    if not endpoint:
        pytest.skip("AWS_ENDPOINT_URL is not set (LocalStack)")

    from botocore.config import Config

    # Short timeouts: if LocalStack is down, skip fast instead of waiting.
    quick = Config(connect_timeout=1, read_timeout=2, retries={"total_max_attempts": 1})
    dynamodb = boto3.resource("dynamodb", config=quick)
    try:
        dynamodb.meta.client.list_tables()
    except Exception:
        pytest.skip(f"LocalStack is not running at {endpoint}")

    # Same keys as infra/localstack/init/03_exchange_rates.py in SecurePay,
    # but its own name so the test never touches the real local table.
    table = dynamodb.create_table(
        TableName=f"test-exchange-rates-{uuid.uuid4().hex[:8]}",
        KeySchema=[
            {"AttributeName": "base", "KeyType": "HASH"},
            {"AttributeName": "rate_date", "KeyType": "RANGE"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "base", "AttributeType": "S"},
            {"AttributeName": "rate_date", "AttributeType": "S"},
        ],
        BillingMode="PAY_PER_REQUEST",
    )
    table.wait_until_exists()
    return table


@pytest.mark.integracion
def test_latest_returns_the_newest_day_saved_in_localstack():
    table = _localstack_table()
    try:
        older = {**_RESULT, "date": "2026-10-01"}
        store.save([_RESULT, older], table=table)

        newest = store.latest(table=table)

        assert newest["rate_date"] == "2026-10-02"
        assert newest["rates"]["COP"] == Decimal("3317.65")
    finally:
        table.delete()
