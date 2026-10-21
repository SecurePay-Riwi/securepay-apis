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

# Same, but into the DynamoDB table (LocalStack), every day since October 1
RATES_OUTPUT=dynamodb RATES_FROM=2026-10-01 uv run python -m securepay_apis.exchange_rates

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

Asks Frankfurter how many COP, EUR and JPY one USD buys, validates the answer
and stores it. Requires internet access and retries up to 3 times on server or
network errors. If the answer is incomplete or a rate is invalid, it fails and
stores nothing.

| Variable | Values | What it does |
|----------|--------|--------------|
| `RATES_OUTPUT` | `file` (default), `dynamodb` | `file` writes `src/securepay_apis/exchange_rates/data/rates_YYYY-MM-DD.json` (Git-ignored); `dynamodb` writes the table |
| `RATES_TABLE` | `pagoseguro-exchange-rates` | DynamoDB table name |
| `RATES_FROM` | unset, or a date like `2026-10-01` | Unset: only today. With a date: every published day from that date up to today |

The table has one item per day: `base` (partition key, always `USD`),
`rate_date` (sort key, `YYYY-MM-DD`), `rates`, `source` and `expires_at`
(DynamoDB deletes the item 30 days after it was written). The decision engine
converts each transaction with the rate of its own date. Frankfurter blends
several providers and usually publishes every day, weekends included; a day
without a rate uses the last earlier day.

To load the table locally, start LocalStack from the SecurePay repository
(it creates the table on start-up) and run:

```bash
RATES_OUTPUT=dynamodb RATES_FROM=2026-10-01 uv run python -m securepay_apis.exchange_rates
```

In AWS the same code runs as a Lambda (`securepay_apis.exchange_rates.handler.handler`)
that EventBridge Scheduler calls once a day; it always writes today's rates to
DynamoDB.

## Local services

PostgreSQL (port 5433) and LocalStack run with the Docker Compose of the
[SecurePay](https://github.com/SecurePay-Riwi/SecurePay) repository (`docker compose up -d`).
LocalStack is only needed for `LISTA_SOURCE=s3` and `RATES_OUTPUT=dynamodb`.

## Repository layout

```
src/securepay_apis/
├── exchange_rates/    # Frankfurter client, DynamoDB store and Lambda handler
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


## Docker

Build the Python 3.12 image with uv from this repository root:

```bash
docker build -t securepay-apis .
```

The standalone container needs the seed list at
`/app/generated/listas/lista_restrictiva.jsonl` (or a custom path in
`SEED_LIST_FILE`). The full Compose stack mounts the shared seed volume and
sets this variable. Health check: http://localhost:8001/health.
