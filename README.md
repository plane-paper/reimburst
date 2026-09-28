# reimburst
Reimbursement automation service

## Individual mode (P1 / P2 / P3)

The receipt path is `POST /receipts` → object storage → ARQ → Azure Document
Intelligence → `GET /receipts/{id}`. Run Postgres and Redis with
`docker compose up -d`, apply the API migrations, start the API and worker, and
set these environment variables in both processes:

```text
DATABASE_URL=postgresql+asyncpg://reimburse:reimburse@localhost:5432/reimburse
REDIS_URL=redis://localhost:6379
AZURE_DI_ENDPOINT=https://<resource>.cognitiveservices.azure.com
AZURE_DI_KEY=<key>
OPENAI_API_KEY=<key>
# OPENAI_CATEGORIZATION_MODEL=gpt-4o-mini
```

After OCR completes, the worker categorizes each line item asynchronously with
taxonomy-constrained structured output. The built-in global taxonomy is
`hotel`, `food`, `essentials`, `transport`, `office_supplies`, `other`, and
`uncategorized`; low-confidence and fallback assignments are returned with a
human-review flag. `GET /receipts/taxonomy` exposes this same taxonomy to the
client.

Confirmed receipts are available in the personal spending report at `/spending`,
including date, merchant, and category filters plus CSV export. At `/requests`,
an individual can select confirmed line items across receipts, specify an
external payer, and generate an editable reimbursement email draft. Generation
runs in ARQ using `OPENAI_SYNOPSIS_MODEL` (default `gpt-4o-mini`); drafts can be
copied or downloaded as `.eml`, then marked sent after the user sends them with
their own email client. Request history retains the covered items and generated
or sent timestamps, preventing already-requested items from being selected
again.

For local development, storage defaults to `STORAGE_BACKEND=local` and writes
to `LOCAL_STORAGE_PATH` (default: `/tmp/reimburst-uploads`). For deployment,
set the following in both the API and worker so they use the same durable,
S3-compatible bucket:

```text
STORAGE_BACKEND=s3
S3_BUCKET=<bucket>
AWS_REGION=<region>
# S3_ENDPOINT_URL=<endpoint>  # required only for S3-compatible providers
```

Credentials are supplied through boto3's normal AWS credential provider chain
(for example, workload identity or `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`).

## Organization workflow (P4)

The organization workspace is available at `/organization`. It includes an
employee view for organization receipt capture, review/confirmation, selecting
confirmed unassigned receipts in one currency, draft creation, and submission.
The approver view lists submitted requests and shows their receipt image,
categorized breakdown, asynchronous synopsis, and immutable audit history;
requests can be approved or rejected with an optional note.

The supporting endpoints are `POST /organization/receipts`,
`GET /organization/receipts/available`, `POST /organization/requests`,
`GET /organization/requests/mine`, `GET /organization/requests/pending`, and
the request submit/approve/reject routes. A failed organization synopsis can be
re-enqueued with `POST /organization/requests/{id}/retry-synopsis`; the workflow
state is unchanged. Receipt previews are available through
`GET /organization/receipts/{id}/image`; organization receipt polling and
confirmation use the scoped `GET /organization/receipts/{id}` and
`PUT /organization/receipts/{id}/confirmation` routes.

## Authentication and roles (P5)

All portal and API workflow requests now require a bearer token. Set a strong,
unique `AUTH_SECRET` in the API environment before starting the service. The web
portal provides registration and sign-in; self-registration creates an
`individual` account only. Individual accounts can use personal receipts,
spending, and outbound requests, but cannot access organization routes.

Organization accounts are provisioned through a trusted operator shell so a
visitor cannot select a privileged role. The command creates the named
organization when needed:

```text
uv run --package api python apps/api/scripts/provision_user.py \
  --email employee@example.com \
  --password '<at-least-12-character-password>' \
  --role employee \
  --organization 'Example Co'
```

Use `--role approver` for approval-queue users or `--role admin` for an
organization administrator (admins may approve requests). Employees only see
their own receipts and requests; approvers only see their organization’s pending
approval queue. The API checks the database role on every request, so changing a
client-side view or a token claim cannot escalate access.

Workflow notifications are stored in the database and appear in the portal’s
Notifications menu. Submitting a request notifies all approvers and admins in
the organization; approving or rejecting it notifies the submitting employee,
including any decision note. Notifications can be marked read and are visible
only to their intended user. Apply the latest Alembic migration before starting
the updated API.

The portal’s protected organization receipt previews and personal-spending CSV
exports are fetched with the active bearer token. A persistent account menu
includes sign-out, and unexpected page failures provide a retry screen. P6 adds
payout dispatch.
