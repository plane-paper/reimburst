# Reimburst

**Turn receipt images into reviewable reimbursement requests.** Reimburst extracts receipt data, categorizes expenses, and supports both personal reimbursement emails and an organization approval workflow.

## What it does

- Upload JPEG, PNG, or WebP receipt images (up to 10 MB).
- Extract merchant, date, currency, totals, tax, and line items with Azure Document Intelligence.
- Categorize line items with a constrained expense taxonomy and flag uncertain classifications for review.
- Reconcile extracted line items against the receipt total before confirmation.
- Track personal spending with date, merchant, and category filters, plus CSV export.
- Generate editable reimbursement-email drafts for external payers; copy, download as `.eml`, and mark them sent.
- Run organization reimbursements from capture through submission, review, approval or rejection, and a manual-payroll CSV payout export.
- Enforce individual, employee, approver, and admin roles; keep request audit history and deliver in-app notifications.

## Architecture

| Component | Responsibility | Local address |
| --- | --- | --- |
| Next.js portal | Sign-in, receipt capture, spending, requests, and organization workflows | <http://localhost:3000> |
| FastAPI service | REST API, authentication, persistence, and job enqueueing | <http://localhost:8000> |
| ARQ worker | OCR, categorization, and AI draft/synopsis jobs | — |
| PostgreSQL | Application data and audit history | `localhost:5432` |
| Redis | Background-job queue | `localhost:6379` |

## Prerequisites

- [Node.js](https://nodejs.org/) with Corepack enabled (the repo pins Yarn 4).
- [Python 3.13+](https://www.python.org/) and [uv](https://docs.astral.sh/uv/).
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) or Docker Engine with Compose.
- An Azure Document Intelligence endpoint and key for receipt extraction.
- An OpenAI API key for line-item categorization and draft/synopsis generation.

## Get running locally

The following starts every local dependency and application component. Run the API, worker, and portal in separate terminals after completing the one-time setup.

### 1. Install dependencies

From the repository root:

```sh
corepack enable
yarn install
uv sync --all-packages
```

### 2. Configure your environment

Copy the template and fill in the required values:

```sh
cp .env.example .env
```

For a standard local setup, use these settings in `.env` (replace the placeholder values):

```dotenv
# Required: receipt extraction and AI assistance
AZURE_DI_ENDPOINT=https://<resource>.cognitiveservices.azure.com
AZURE_DI_KEY=<azure-document-intelligence-key>
OPENAI_API_KEY=<openai-api-key>

# Required: service infrastructure and authentication
DATABASE_URL=postgresql+asyncpg://reimburse:reimburse@localhost:5432/reimburse
REDIS_URL=redis://localhost:6379
AUTH_SECRET=<a-long-random-secret>

# Required by the browser app; this is safe to expose to the browser
NEXT_PUBLIC_API_URL=http://localhost:8000
CORS_ORIGINS=http://localhost:3000

# Optional: these are the local-development defaults
STORAGE_BACKEND=local
LOCAL_STORAGE_PATH=/tmp/reimburst-uploads
# OPENAI_CATEGORIZATION_MODEL=gpt-4o-mini
# OPENAI_SYNOPSIS_MODEL=gpt-4o-mini
```

Load the variables into each terminal before starting the API or worker:

```sh
set -a
source .env
set +a
```

Keep `.env` private. It is ignored by Git and must never be committed.

### 3. Start PostgreSQL and Redis

```sh
docker compose up -d
docker compose ps
```

Both services should report healthy before continuing. To stop them later, run `docker compose down`; named volumes preserve local data.

### 4. Apply database migrations

With the environment loaded:

```sh
uv run --package api alembic -c apps/api/alembic.ini upgrade head
```

### 5. Start the applications

In terminal 1, start the API:

```sh
set -a; source .env; set +a
yarn workspace api dev
```

In terminal 2, start the background worker:

```sh
set -a; source .env; set +a
uv run --package worker arq worker.settings.WorkerSettings
```

In terminal 3, start the portal:

```sh
set -a; source .env; set +a
yarn dev
```

Open <http://localhost:3000>. You can verify the API independently at <http://localhost:8000/health>, which returns `{"status":"ok"}`.

### 6. Create an account and try the flow

1. Register in the portal with an email and a password of at least 12 characters.
2. Select **Scan Receipt** and upload a receipt image.
3. Wait for extraction and categorization to complete, inspect the values, and confirm the receipt.
4. Use **Spending** to review confirmed items or **My Requests** to produce an editable reimbursement email.

The worker performs OCR and AI tasks asynchronously. If a receipt remains in a processing state, confirm that the worker is running and that Azure, OpenAI, Redis, and database configuration is available to it.

## Workflows and roles

### Personal reimbursement

Individual users can capture and confirm receipts, inspect their categorized spending, export a filtered CSV, and select confirmed line items to generate a reimbursement email for an external payer. Items included in generated or sent requests cannot be selected again. Email artifacts remain editable and can be copied or downloaded before the user sends them through their own mail client.

### Organization reimbursement

Organization employees capture and confirm receipts, select unassigned receipts in a single currency, create a draft, and submit it. Approvers and admins see pending requests with receipt previews, categorized breakdowns, an AI-generated synopsis, and immutable audit events; they can approve or reject with an optional note. Organization admins can export an approved request as a payroll CSV, which marks it paid. Payout exports are idempotent: repeating an export returns the same frozen row rather than creating a duplicate payout.

Self-registration only creates an `individual` account. Provision organization accounts from a trusted operator shell:

```sh
set -a; source .env; set +a
uv run --package api python apps/api/scripts/provision_user.py \
  --email employee@example.com \
  --password '<at-least-12-character-password>' \
  --role employee \
  --organization 'Example Co'
```

Use `--role approver` for reviewers and `--role admin` for organization administrators. Role checks are enforced by the API; a browser-side change cannot grant additional access.

## Configuration and deployment notes

| Setting | Required | Purpose |
| --- | --- | --- |
| `DATABASE_URL` | Yes | Async PostgreSQL connection URL. |
| `REDIS_URL` | Yes | ARQ job queue connection URL. |
| `AUTH_SECRET` | Yes | Strong, unique secret used to sign 12-hour bearer tokens. |
| `AZURE_DI_ENDPOINT`, `AZURE_DI_KEY` | Yes for receipt processing | Azure Document Intelligence credentials. |
| `OPENAI_API_KEY` | Yes for categorization and generated drafts | OpenAI credentials for background AI jobs. |
| `NEXT_PUBLIC_API_URL` | Yes for a non-default API URL | Browser-visible API base URL. |
| `CORS_ORIGINS` | Production | Comma-separated allowed portal origins; defaults to `http://localhost:3000`. |
| `STORAGE_BACKEND` | No | `local` (default) or `s3`. |
| `LOCAL_STORAGE_PATH` | No | Local receipt directory; defaults to `/tmp/reimburst-uploads`. |

For production, use durable object storage and set the same values for the API and worker:

```dotenv
STORAGE_BACKEND=s3
S3_BUCKET=<bucket>
AWS_REGION=<region>
# S3_ENDPOINT_URL=<endpoint>  # Needed for an S3-compatible provider
```

Provide AWS credentials through the standard boto3 credential chain, such as workload identity or `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`. Use a production database and Redis instance, set a unique `AUTH_SECRET`, restrict `CORS_ORIGINS` to deployed portal origins, and run migrations before deploying a new API version.

## Developer commands

```sh
# Web application checks and production build
yarn lint
yarn typecheck
yarn build

# Python checks and API tests
uv run --package api ruff check .
uv run --package api pytest apps/api/tests
uv run --package api mypy py/shared/shared apps/api/app apps/worker/worker

# Refresh the generated TypeScript contract from the API schema
yarn contract:generate
```

## Project layout

```text
apps/api/       FastAPI application, Alembic migrations, and provisioning scripts
apps/worker/    ARQ background jobs for extraction and AI enrichment
apps/web/       Next.js portal
packages/       Shared TypeScript contract and utilities
py/shared/      Shared Python models, OCR, storage, and AI providers
```

## Roadmap

The items below are planned directions, not features currently available in the product:

- Configurable organization-specific taxonomies and reimbursement policies.
- Direct accounting, payroll, and email-provider integrations.
- Multi-currency conversion and policy-aware per-diem support.
- Receipt deduplication, stronger anomaly detection, and richer review controls.
- Team administration, reporting dashboards, and export integrations.
- Production deployment automation, observability, and operational runbooks.

## Troubleshooting

- **API returns authentication errors:** ensure `AUTH_SECRET` is present in the API process and sign in again to obtain a new token.
- **Receipt processing fails or stalls:** check the worker logs first, then verify `REDIS_URL`, `DATABASE_URL`, Azure credentials, and the receipt format/size.
- **Categorization or draft generation fails:** verify `OPENAI_API_KEY`; extraction can complete even if a later AI job fails.
- **Browser cannot reach the API:** ensure the API is on port 8000, `NEXT_PUBLIC_API_URL` is correct when the portal starts, and `CORS_ORIGINS` includes the portal origin.
- **Database schema errors after pulling changes:** rerun the Alembic upgrade command from the setup steps.
