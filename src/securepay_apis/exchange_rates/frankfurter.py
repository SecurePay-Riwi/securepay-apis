"""Frankfurter exchange rate client (F6).

Frankfurter is a public API: no authentication, no rate limits. Version 2
includes COP via BANREP (v1 does not). See the project logbook.

Called once a day. In AWS, from a Lambda triggered by EventBridge Scheduler.
"""

import json
import logging
import time
from decimal import Decimal
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Without a custom User-Agent, Frankfurter responds 403. The default
# Python UA is blocked.
_URL = "https://api.frankfurter.dev/v2/rates"
_USER_AGENT = "securepay-exchange-rates"

# The three currencies we convert to. USD is the base, always 1.
_CURRENCIES = ["COP", "EUR", "JPY"]
_BASE = "USD"

# The API is fast but not infinite. 10s is a reasonable ceiling for a
# daily task that runs in a Lambda with a 30s budget.
_TIMEOUT = 10.0

# Retries only apply to 5xx and network errors. A 4xx means we sent
# something wrong and there is no point in repeating it.
_RETRIES = 3


def fetch() -> dict[str, Any]:
    """Call Frankfurter and return a validated dictionary.

    Returns:
        {
            "date": "2026-10-14",
            "rates": {"USD": 1, "COP": 3317.65, "EUR": 0.88286, "JPY": 157.78},
            "source": "<full url>",
        }

    Raises if the response is incomplete, inconsistent or has invalid
    rates. The task never writes partial data: either everything is
    valid, or nothing is stored.
    """
    params = {"base": _BASE, "quotes": ",".join(_CURRENCIES)}
    records = _get(params)
    return _validate(records, _url(params))


def fetch_range(start: str, end: str | None = None) -> list[dict[str, Any]]:
    """Rates for every published day between start and end (both included).

    Used to load past days into the table, for example from the generator's
    reference date (2026-10-01) up to today. Without end, Frankfurter goes
    up to today. Frankfurter blends several providers, so it usually has a
    row for every day, weekends included; a day without one is simply
    missing, and readers use the last earlier day.

    Returns one dictionary per day, shaped like fetch(), oldest first.
    A day where a currency is missing is skipped and logged, because the
    providers do not always publish on the same days (COP comes from
    BANREP, EUR and JPY from the ECB). Any invalid rate fails the whole
    call, as in fetch().
    """
    params = {"base": _BASE, "quotes": ",".join(_CURRENCIES), "from": start}
    if end:
        params["to"] = end
    records = _get(params)
    url = _url(params)

    by_date: dict[str, list[dict]] = {}
    for record in records:
        by_date.setdefault(record["date"], []).append(record)

    days = []
    for date in sorted(by_date):
        quotes = {r["quote"] for r in by_date[date]}
        if quotes != set(_CURRENCIES):
            logger.warning("Skipping %s: Frankfurter returned only %s", date, quotes)
            continue
        days.append(_validate(by_date[date], url))

    if not days:
        raise ValueError(f"Frankfurter returned no complete day from {start}")
    return days


def _get(params: dict) -> list[dict]:
    """Make the request and parse the rows with Decimal rates."""
    headers = {"User-Agent": _USER_AGENT}
    response = _request_with_retries(params, headers)

    # parse_float=Decimal: boto3 rejects floats when writing to DynamoDB.
    # Parsing at the source avoids converting later.
    return json.loads(response.text, parse_float=Decimal)


def _url(params: dict) -> str:
    """The full URL, kept with the rates as evidence of where they came from."""
    return f"{_URL}?{'&'.join(f'{k}={v}' for k, v in params.items())}"


def _request_with_retries(params: dict, headers: dict) -> httpx.Response:
    """Make the HTTP request, retrying on 5xx with increasing waits."""
    last_error: Exception | None = None

    for attempt in range(_RETRIES):
        try:
            response = httpx.get(
                _URL, params=params, headers=headers, timeout=_TIMEOUT
            )

            # httpx.raise_for_status does not distinguish 4xx from 5xx,
            # so we raise the 5xx ourselves to catch it and retry.
            if response.status_code >= 500:
                raise httpx.HTTPStatusError(
                    f"Frankfurter returned {response.status_code}",
                    request=response.request,
                    response=response,
                )
            response.raise_for_status()
            return response

        except (httpx.HTTPStatusError, httpx.RequestError) as error:
            # 4xx is our fault: fail fast, do not retry.
            if (
                isinstance(error, httpx.HTTPStatusError)
                and error.response.status_code < 500
            ):
                raise

            last_error = error
            if attempt < _RETRIES - 1:
                time.sleep(2 ** attempt)  # 1s, then 2s, then 4s

    raise RuntimeError(
        f"Frankfurter did not respond after {_RETRIES} attempts: {last_error}"
    )


def _validate(records: list[dict], url: str) -> dict[str, Any]:
    """Validate the response before anyone uses it.

    The three checks are non-negotiable:
    - All expected currencies are present.
    - All records share the same date (Frankfurter can return a mix).
    - Every rate is positive.

    Weekends and holidays: the central bank does not publish, so the API
    returns Friday's date. We keep whatever date the API says, never
    invent one.
    """
    if not records:
        raise ValueError("Frankfurter returned an empty response")

    received_currencies = {r["quote"] for r in records}
    expected_currencies = set(_CURRENCIES)
    if received_currencies != expected_currencies:
        raise ValueError(
            f"Frankfurter returned {received_currencies}, "
            f"expected {expected_currencies}"
        )

    dates = {r["date"] for r in records}
    if len(dates) != 1:
        raise ValueError(f"Record dates do not match: {dates}")
    date = dates.pop()

    # USD is the base, its rate is 1 by definition.
    rates: dict[str, Decimal] = {_BASE: Decimal(1)}
    for record in records:
        if record["rate"] <= 0:
            raise ValueError(f"Invalid rate for {record['quote']}: {record['rate']}")
        rates[record["quote"]] = record["rate"]

    return {
        "date": date,
        "rates": rates,
        "source": url,
    }