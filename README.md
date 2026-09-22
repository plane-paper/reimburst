# reimburst
Reimbursement automation service

## Core extraction (P1)

The receipt path is `POST /receipts` → object storage → ARQ → Azure Document
Intelligence → `GET /receipts/{id}`. Run Postgres and Redis with
`docker compose up -d`, apply the API migrations, start the API and worker, and
set these environment variables in both processes:

```text
DATABASE_URL=postgresql+asyncpg://reimburse:reimburse@localhost:5432/reimburse
REDIS_URL=redis://localhost:6379
AZURE_DI_ENDPOINT=https://<resource>.cognitiveservices.azure.com
AZURE_DI_KEY=<key>
```

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
