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
