"""Tests for the entry points: the local command and the Lambda handler.

Frankfurter and DynamoDB are replaced, so no internet or LocalStack.
"""

from decimal import Decimal
from unittest.mock import patch

import pytest

from securepay_apis.exchange_rates import __main__ as cli
from securepay_apis.exchange_rates import handler

_RESULT = {
    "date": "2026-10-02",
    "rates": {"USD": Decimal(1), "COP": Decimal("3317.65")},
    "source": "https://api.frankfurter.dev/v2/rates",
}


def test_file_is_the_default_output(monkeypatch, tmp_path):
    monkeypatch.delenv("RATES_OUTPUT", raising=False)
    monkeypatch.delenv("RATES_FROM", raising=False)
    monkeypatch.setattr(cli, "_DATA_DIR", tmp_path)

    with patch.object(cli.frankfurter, "fetch", return_value=_RESULT), \
         patch.object(cli.store, "save") as save:
        cli.main()

    assert (tmp_path / "rates_2026-10-02.json").exists()
    save.assert_not_called()


def test_dynamodb_output_with_a_start_date_saves_the_whole_range(monkeypatch):
    monkeypatch.setenv("RATES_OUTPUT", "dynamodb")
    monkeypatch.setenv("RATES_FROM", "2026-10-01")
    days = [_RESULT, {**_RESULT, "date": "2026-10-05"}]

    with patch.object(cli.frankfurter, "fetch_range", return_value=days) as fetch_range, \
         patch.object(cli.store, "save", return_value=2) as save:
        cli.main()

    fetch_range.assert_called_once_with("2026-10-01")
    save.assert_called_once_with(days)


def test_unknown_output_fails(monkeypatch):
    monkeypatch.setenv("RATES_OUTPUT", "s3")

    with pytest.raises(ValueError, match="RATES_OUTPUT"):
        cli.main()


def test_handler_saves_todays_rates():
    with patch.object(handler.frankfurter, "fetch", return_value=_RESULT), \
         patch.object(handler.store, "save") as save:
        response = handler.handler({}, None)

    save.assert_called_once_with([_RESULT])
    assert response == {"date": "2026-10-02"}


def test_handler_writes_nothing_when_frankfurter_fails():
    with patch.object(handler.frankfurter, "fetch", side_effect=RuntimeError("down")), \
         patch.object(handler.store, "save") as save:
        with pytest.raises(RuntimeError):
            handler.handler({}, None)

    save.assert_not_called()
