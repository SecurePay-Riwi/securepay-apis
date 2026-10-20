"""Exchange rates in DynamoDB: table pagoseguro-exchange-rates.

One item per published day:

    base        partition key, always "USD"
    rate_date   sort key, "YYYY-MM-DD" (the date Frankfurter gives)
    rates       {"USD": 1, "COP": 3317.65, "EUR": 0.88286, "JPY": 157.78}
    source      the URL that was called, as evidence
    expires_at  epoch seconds; DynamoDB TTL deletes the item after that

With base as the partition key and rate_date as the sort key, one query
returns the latest day, or every day, already ordered. The engine loads
the whole table (about 30 items) and converts each transaction with the
rate of its own date.

boto3 reads AWS_ENDPOINT_URL from the environment: locally it points to
LocalStack, in AWS it is not set and boto3 uses the real table with the
Lambda's role. The code does not change.
"""

import os
from datetime import datetime, timedelta, timezone
from typing import Any

from dotenv import load_dotenv

load_dotenv()

BASE = "USD"

# How long an item lives after it is written. Counted from the load, not
# from rate_date: a past day loaded today must not expire at once.
RETENTION_DAYS = 30


def table_name() -> str:
    return os.getenv("RATES_TABLE", "pagoseguro-exchange-rates")


def _table():
    # Import here: the file mode and the tests do not need boto3.
    import boto3

    return boto3.resource("dynamodb").Table(table_name())


def to_item(result: dict[str, Any], now: datetime | None = None) -> dict[str, Any]:
    """Turn the result of frankfurter.fetch() into a DynamoDB item.

    The rates are already Decimal (frankfurter parses them that way), so
    boto3 accepts them as they are.
    """
    now = now or datetime.now(timezone.utc)
    expires = now + timedelta(days=RETENTION_DAYS)
    return {
        "base": BASE,
        "rate_date": result["date"],
        "rates": result["rates"],
        "source": result["source"],
        "expires_at": int(expires.timestamp()),
    }


def save(results: list[dict[str, Any]], table=None) -> int:
    """Write one item per day and return how many were written.

    Writing the same day again replaces it with the same values, so a
    retried run (EventBridge retries a failed Lambda) does no harm.
    """
    table = table or _table()
    now = datetime.now(timezone.utc)
    with table.batch_writer() as batch:
        for result in results:
            batch.put_item(Item=to_item(result, now))
    return len(results)


def latest(table=None) -> dict[str, Any] | None:
    """The most recent day in the table, or None if it is empty."""
    table = table or _table()
    # Imported here for the same reason as boto3 above.
    from boto3.dynamodb.conditions import Key

    response = table.query(
        KeyConditionExpression=Key("base").eq(BASE),
        ScanIndexForward=False,  # newest first
        Limit=1,
    )
    items = response.get("Items", [])
    return items[0] if items else None

