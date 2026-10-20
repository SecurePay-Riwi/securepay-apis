"""Local entry point: fetch the rates and store them.

    uv run python -m securepay_apis.exchange_rates

Where they go depends on RATES_OUTPUT:

- file (default): a JSON per day in exchange_rates/data/, ignored by Git.
  Needs only internet, no LocalStack.
- dynamodb: the pagoseguro-exchange-rates table (LocalStack locally, via
  AWS_ENDPOINT_URL).

Without RATES_FROM it stores today's rates, like the daily Lambda
(handler.py). With RATES_FROM=2026-10-01 it stores every published day
from that date up to today, so the engine can convert the simulated
transactions of those days with their own rate.
"""

import json
import logging
import os
from pathlib import Path

# store loads .env on import, before RATES_OUTPUT and RATES_FROM are read.
from securepay_apis.exchange_rates import frankfurter, store

logger = logging.getLogger(__name__)

# Local folder for the JSON files. Ignored by .gitignore.
_DATA_DIR = Path(__file__).parent / "data"

_OUTPUTS = ("file", "dynamodb")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    output = os.getenv("RATES_OUTPUT", "file")
    if output not in _OUTPUTS:
        raise ValueError(f"RATES_OUTPUT must be one of {_OUTPUTS}, not {output!r}")
    start = os.getenv("RATES_FROM")

    print("Fetching rates from Frankfurter...")
    results = frankfurter.fetch_range(start) if start else [frankfurter.fetch()]

    for result in results:
        rates = ", ".join(f"{rate} {currency}" for currency, rate in result["rates"].items())
        print(f"  {result['date']}: 1 USD = {rates}")

    if output == "dynamodb":
        count = store.save(results)
        print(f"\n{count} day(s) saved to DynamoDB table {store.table_name()}")
    else:
        for result in results:
            path = _save_json(result)
        print(f"\n{len(results)} day(s) saved to {path.parent}")


def _save_json(result: dict) -> Path:
    """Write the rates of one day to a JSON file.

    Decimal values are serialized as strings. JSON has no native Decimal
    type, and storing them as floats would lose precision.
    """
    _DATA_DIR.mkdir(parents=True, exist_ok=True)

    serializable = {
        "date": result["date"],
        "source": result["source"],
        "rates": {currency: str(rate) for currency, rate in result["rates"].items()},
    }

    path = _DATA_DIR / f"rates_{result['date']}.json"
    path.write_text(
        json.dumps(serializable, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return path


if __name__ == "__main__":
    main()
