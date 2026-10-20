# securepay-apis

API data sources for the SecurePay Antifraude project.

## Sources

| ID | Source | Type | Frequency |
|----|--------|------|-----------|
| F6 | Exchange rates — [Frankfurter API](https://api.frankfurter.app) | Public API | Daily |
| F7 | Restricted list (sanctions / PEP) | Simulated REST API | On demand |

## Setup

```bash
git clone https://github.com/SecurePay-Riwi/securepay-apis.git
cd securepay-apis
cp .env.example .env
uv sync
```

## Usage

```bash
# Fetch and store today's exchange rates
uv run python -m exchange_rates.fetch

# Query the restricted list
uv run python -m restricted_list.query
```

## Dependencies

- [`securepay-shared`](https://pypi.org/project/securepay-shared/) — shared models, DB and config
