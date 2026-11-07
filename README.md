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

Interactive docs with examples of every response (Swagger): http://localhost:8001/docs.

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
| `RATES_FROM` | unset, or a date like `2026-10-01` | Unset: the newest day with the three currencies. With a date: every published day from that date up to today |

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

In AWS the same code runs as the Lambda `securepay-dev-exchange-rates`
(`securepay_apis.exchange_rates.handler.handler`, this repository's image) that
EventBridge Scheduler calls once a day at 11:00 Bogotá; it writes the newest
day of the last week where COP, EUR and JPY all have a rate (on weekends,
Friday: the ECB dates EUR and JPY on Friday and BANREP dates COP on the
Monday its TRM applies until) to the DynamoDB table `securepay-dev-exchange-rates`
(`RATES_TABLE`). Terraform in SecurePay creates it; see "Deploy" below.

## Local services

PostgreSQL (port 5433) and LocalStack run with the Docker Compose of the
[SecurePay](https://github.com/SecurePay-Riwi/SecurePay) repository (`docker compose up -d`).
LocalStack is only needed for `LISTA_SOURCE=s3` and `RATES_OUTPUT=dynamodb`.

## CI

Every pull request to `main` runs `.github/workflows/ci.yml`, the same
checks as SecurePay: `lint` (ruff check and format),
`secret-scan` (gitleaks over the whole history) and `tests` (pytest,
without PostgreSQL or LocalStack). Run them locally before pushing:

```bash
uv run ruff format .
uv run ruff check .
uv run pytest
```

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


## Docker image (MAG-31)

Build the Python 3.12/uv image from this repository root. It installs locked production dependencies and starts the restricted-list API on port 8001 by default.

```bash
docker build -t securepay-apis .
docker run --rm --env-file .env -p 8001:8001 securepay-apis
```

For the full local ecosystem, use Docker Compose in the `SecurePay` repository; it configures the generated restricted-list file and LocalStack endpoint.

The same image runs as a Lambda: `awslambdaric` is a dependency, and Lambda
starts it with `python -m awslambdaric securepay_apis.exchange_rates.handler.handler`
instead of uvicorn. Build it with `docker build --provenance=false` when it goes
to ECR (Lambda rejects image indexes).

## Deploy

On every merge to `main`, `.github/workflows/deploy.yml` builds the image,
pushes it to ECR (`securepay-dev-apis`) tagged with the short commit and
updates the `securepay-dev-exchange-rates` Lambda. It authenticates with
GitHub's OIDC token as the role `securepay-dev-deploy-apis`, which only trusts
this repository's `main` and may only push this image and update that Lambda;
there are no AWS keys in GitHub. When the dev environment is destroyed it ends
green with a notice. It can also be run by hand (Actions > Deploy > Run
workflow), for example right after `terraform apply`.

Once per environment, set the repository variable `AWS_DEPLOY_ROLE_ARN`
(Settings > Secrets and variables > Actions > Variables) to the output of
`aws iam get-role --role-name securepay-dev-deploy-apis --query Role.Arn --output text`.
The whole flow (first apply, push, apply with `apis_image_tag`, first run) is
in SecurePay's guide: https://securepay-riwi.github.io/SecurePay/docs/getting-started/deploy-aws-terraform#9-load-the-daily-exchange-rates
