# securepay-apis

Simulated external APIs for the SecurePay Antifraude project.

| Source | Type |
|--------|------|
| Frankfurter exchange rates | Public REST API (no key needed) |
| Restricted list (PEP / sanctions) | Simulated REST API of an external provider |

## Setup

```bash
git clone https://github.com/SecurePay-Riwi/securepay-apis.git
cd securepay-apis
cp .env.example .env
uv sync
```

## Usage

```bash
# Fetch today's exchange rates from Frankfurter and save them to JSON
uv run python -m securepay_apis.exchange_rates

# Start the restricted-list API (a slow, unreliable external provider on purpose)
uv run uvicorn securepay_apis.restricted_list.main:app --port 8001

# Run the tests
uv run pytest
```

### Restricted-list API endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /lista` | Full list, used by the daily cache load |
| `GET /lista/{documento}` | Single-document lookup, fallback when the cache is unavailable |
| `GET /health` | Liveness check (no artificial latency) |

The service adds random latency (50 to 3000 ms) and returns 503 on about 5 % of
requests, so the engine has to use a cache and a circuit breaker. Both values
are configurable in `.env`.

The list comes from **securepay-seed**. With `LISTA_SOURCE=file` the service reads
`generated/listas/lista_restrictiva.jsonl`, here or in `../securepay-seed/`;
with `LISTA_SOURCE=s3` it reads the provider bucket (LocalStack locally).

### Exchange rates

Writes `src/securepay_apis/exchange_rates/data/rates_YYYY-MM-DD.json` (Git-ignored).
Requires internet access and retries up to 3 times on server or network errors.

## Local services

PostgreSQL (port 5433) and LocalStack run with the Docker Compose of the
[SecurePay](https://github.com/SecurePay-Riwi/SecurePay) repository (`docker compose up -d`).
LocalStack is only needed for `LISTA_SOURCE=s3`.

## Repository layout

```
src/securepay_apis/
├── exchange_rates/    # Frankfurter client: python -m securepay_apis.exchange_rates
└── restricted_list/   # FastAPI app: securepay_apis.restricted_list.main:app
tests/
├── exchange_rates/
└── restricted_list/
```

All code lives in one package under `src/`; tests mirror it under `tests/`.
Read [AGENTS.md](AGENTS.md) before adding folders or modules.

## Working with the other repositories

The repositories pass data through files (and through S3 in AWS), never through
imports. Clone them side by side in the same folder and each one finds the files
the others produce, without setting paths by hand:

```
SecurePay-Riwi/
├── securepay-seed/        # PostgreSQL master data + restricted list export
├── securepay-generator/   # reads the seed, writes generated/instance-*/
├── securepay-csv/         # Kaggle downloads + partner statements (reads the generator)
└── securepay-apis/        # restricted-list service (reads the seed export)
```

Environment variables still override every path (see `.env.example`).
