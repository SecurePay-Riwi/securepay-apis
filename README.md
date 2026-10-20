# securepay-apis

External API integrations for the SecurePay Antifraude project.

## Data sources

| ID | Source | Type |
|----|--------|------|
| F6 | Frankfurter — live exchange rates | Public REST API (no key needed) |
| F7 | Restricted list (PEP / sanctions) | Simulated REST API (runs locally) |

## Setup

```bash
git clone https://github.com/SecurePay-Riwi/securepay-apis.git
cd securepay-apis
cp .env.example .env
uv sync   # installs securepay-shared from PyPI automatically
```

## Usage

```bash
# Fetch today's exchange rates from Frankfurter and save to JSON
uv run python -m sources.apis.exchange_rates

# Start the restricted-list API (simulates a slow, unreliable external provider)
uv run uvicorn sources.apis.restricted_list.main:app --port 8001

# Run tests
uv run pytest
```

### Restricted-list API endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /lista` | Full list — used by the daily cache-load task |
| `GET /lista/{documento}` | Single-document lookup — fallback when cache is unavailable |
| `GET /health` | Liveness check (no artificial latency) |

The service intentionally adds random latency (50–3000 ms) and returns 503 on ~5 % of
requests to force the engine to implement a circuit breaker and cache. Values are
configurable via `.env`.

### Exchange rates

Writes `sources/apis/exchange_rates/data/rates_YYYY-MM-DD.json` (Git-ignored).
Requires internet access. Retries up to 3 times on server/network errors.

## Dependencies

- [`securepay-shared`](https://pypi.org/project/securepay-shared/) — shared models, DB and config
- The restricted-list service needs the seed export (`generated/listas/lista_restrictiva.jsonl`)
  produced by the **securepay-seed** repo.
