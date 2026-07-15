# Reimbursement Automation Service — Specification

> **Document purpose.** This is a machine-readable project specification. It defines *what* the system does, *what* it is built with, and *in what order* it is built. Requirements carry stable IDs (`FR-*`, `NFR-*`, `INT-*`) so they can be referenced unambiguously. Decisions marked **DECIDED** are settled; items marked **DEFERRED** are explicitly out of the current scope but designed for.

---

## 1. Overview

A web service that automates employee expense reimbursement end-to-end. An employee photographs a receipt; the system extracts and categorizes the line items; the employee confirms (and may correct) the result; the system generates a natural-language request synopsis; an approver reviews and approves; funds are dispensed (via payroll/HR integration, or via export in early versions).

**Product model (DECIDED):** Build as an **internal single-organization tool first**, architected so it can generalize to **multi-tenant B2B SaaS** later. Multi-tenancy, generic SSO/SAML, and organization management are **DEFERRED** in implementation but must not be architecturally precluded.

**Two usage modes (DECIDED):** The system supports two distinct modes that share the same receipt-capture → extraction → categorization → confirmation pipeline, then diverge:

1. **Organization mode** — a user belongs to an organization and submits reimbursement requests into an internal approval workflow that ends in funds being dispensed (payroll integration or export).
2. **Individual mode** — a standalone user with no organization uses the app to track personal spending, generate spending reports, and produce **outbound reimbursement requests** (e.g. an email or document) for a chosen set of items, addressed to an external payer (an employer, client, or other party). There is no internal approver and no payroll dispensing in this mode; the system's output is a report and/or a request artifact the user sends themselves.

A single account may be individual-only, organization-affiliated, or both.

**Primary user roles:**
- **Individual user** — an unaffiliated user; scans receipts, tracks/reports spending, and generates outbound reimbursement requests by selecting specific items.
- **Employee** — an organization member who submits reimbursement requests into the internal workflow.
- **Approver** — reviews and approves/rejects organization requests (supervisor / HR / employer).
- **Admin** — manages organization settings, categories, users, and integrations.

**Canonical happy-path flow — Organization mode:**
```
Employee scans receipt
  → System extracts line-item cost breakdown + merchant + date + total
  → System categorizes each line item into a fund category
  → Employee reviews, optionally corrects, and confirms
  → System generates an LLM request synopsis
  → Approver reviews and approves (or rejects)
  → Funds dispensed (payroll integration) OR exported for payroll (fallback)
```

**Canonical happy-path flow — Individual mode:**
```
Individual user scans receipt(s)
  → System extracts line-item breakdown + merchant + date + total
  → System categorizes each line item
  → User reviews, optionally corrects, and confirms
  → User views spending reports/analytics across their history
  → User selects specific items to reimburse
  → System generates an LLM request synopsis + an outbound request artifact (email draft / document)
  → User sends the request to an external payer themselves
```

**Explicitly interactive user actions (only these require human input):** (1) scanning/uploading a receipt, (2) confirming the extracted breakdown, (3) in organization mode, approving/rejecting a request; in individual mode, selecting items and confirming generation/sending of an outbound request. Correction of extracted data is an *optional* sub-action of confirmation (see `FR-CONF-02`).

---

## 2. Glossary

| Term | Definition |
|---|---|
| **Line item** | A single purchased entry on a receipt: `{ description, amount (integer cents), currency, category }`. |
| **Fund category** | A predefined spending bucket (e.g. hotel, food, essentials, transport). Defined by a fixed taxonomy per organization. |
| **Reimbursement request** | The unit of workflow. Contains one or more receipts, their line items, a synopsis, a status, and an audit trail. |
| **Spending report** | An aggregated, filterable view of an individual user's captured spending over time, grouped by category, merchant, or date range. Exportable. |
| **Outbound request artifact** | A user-facing deliverable generated in individual mode from selected items — an email draft and/or a document (PDF) — that the user sends to an external payer. Distinct from the internal-workflow reimbursement request. |
| **External payer** | The party an individual user requests reimbursement from (employer, client, etc.). Not a system user; addressed only via the outbound artifact. |
| **Reconciliation** | Check that summed line-item amounts equal the extracted receipt total, within tolerance. |
| **Synopsis** | LLM-generated natural-language summary of a request, produced at submission from confirmed data. |
| **PayrollProvider** | An abstraction over payout dispatch. Implementations: CSV export (fallback), Employment Hero, Workday. |
| **OcrProvider** | An abstraction over receipt extraction. Implementations: cloud document service (default), self-hosted OCR (deferred). |

---

## 3. Functional Requirements

### 3.1 Receipt capture & extraction (`FR-OCR`)
- **FR-OCR-01** — Employee can upload or capture a receipt image from a web client, including directly from a mobile device camera.
- **FR-OCR-02** — Uploaded receipt images are stored in object storage; only a storage key/URL is persisted in the database (never the image blob in a DB row).
- **FR-OCR-03** — The system extracts structured data from a receipt: merchant, date, currency, total, tax, and a list of line items (description + amount).
- **FR-OCR-04** — Extraction runs behind a swappable `OcrProvider` interface. Default implementation calls a cloud document-understanding service (AWS Textract `AnalyzeExpense` or Azure AI Document Intelligence receipt model). A self-hosted implementation is **DEFERRED** but must fit the same interface.
- **FR-OCR-05** — Extraction executes as an asynchronous background job; the client shows a pending state and receives the result on completion.
- **FR-OCR-06** — All monetary amounts are represented and stored as **integer minor units (cents)** with an explicit ISO-4217 currency code. Floating-point money representation is prohibited (see `NFR-05`).

### 3.2 Categorization (`FR-CAT`)
- **FR-CAT-01** — Each extracted line item is assigned a fund category from a fixed, organization-configurable taxonomy.
- **FR-CAT-02** — Categorization uses an LLM constrained to the taxonomy via structured/enumerated output. The taxonomy is defined once in a shared location and referenced by client, backend, and prompt.
- **FR-CAT-03** — A line item that cannot be confidently categorized is assigned a fallback/`uncategorized` value and flagged for human review.

### 3.3 Confirmation (`FR-CONF`)
- **FR-CONF-01** — The employee is shown the full extracted-and-categorized breakdown before submission.
- **FR-CONF-02** — The employee can edit any line item (amount, description, category) prior to confirming. Confirmation is **not** read-only.
- **FR-CONF-03** — Before submission, the system runs a reconciliation check (sum of line items vs. extracted total). A mismatch beyond tolerance blocks silent submission and surfaces the discrepancy to the employee.
- **FR-CONF-04** — On confirmation, the request transitions to `submitted` and its data is frozen as the basis for synopsis generation and approval.

### 3.4 Synopsis generation (`FR-SYN`)
- **FR-SYN-01** — On submission, the system generates a natural-language synopsis of the request from the confirmed data.
- **FR-SYN-02** — Synopsis generation runs as an asynchronous job and is stored on the request.

### 3.5 Approval workflow (`FR-WF`)
- **FR-WF-01** — A reimbursement request follows an explicit state machine: `draft → submitted → approved → paid`, with `rejected` reachable from `submitted`.
- **FR-WF-02** — An approver can view submitted requests, their receipts, breakdown, and synopsis, and approve or reject with an optional note.
- **FR-WF-03** — Every state transition writes an entry to an immutable audit log (see `NFR-04`).
- **FR-WF-04** — Approval authority is enforced by role (see `FR-AUTH`); an employee cannot approve their own request.

### 3.6 Individual mode — reports & outbound requests (`FR-IND`)
> Applies to **individual users** only. Reuses `FR-OCR-*`, `FR-CAT-*`, and `FR-CONF-*` for capture through confirmation; the requirements below cover what happens *after* confirmation in individual mode.
- **FR-IND-01** — A confirmed receipt captured by an individual user is retained in that user's personal spending history, independent of any organization.
- **FR-IND-02** — The user can view a **spending report**: an aggregated view of their captured spending, filterable by date range, category, and merchant, with totals per group. (See `FR-CAT` — categorization drives the grouping.)
- **FR-IND-03** — The spending report is exportable (CSV and/or PDF) for the user's own records.
- **FR-IND-04** — The user can select a specific subset of line items (across one or more receipts) to include in a reimbursement request.
- **FR-IND-05** — From the selected items, the system generates an LLM synopsis and an **outbound request artifact**: an email draft (subject + body, itemized) and/or a document (PDF), addressed to a user-specified external payer.
- **FR-IND-06** — The user can review and edit the generated artifact before it is finalized. Generation is not send-on-generate.
- **FR-IND-07** — Sending is user-driven. Minimum viable: the artifact is downloadable/copyable and the user sends it via their own email client. Optional later: send directly via an integrated mail provider.
- **FR-IND-08** — An individual outbound request records which items it covered and when it was generated/sent, so the user can track what has been requested versus not-yet-requested. No internal approver or payroll dispensing is involved.

### 3.7 Payout / dispensing (`FR-PAY` / `INT`)
- **FR-PAY-01** — Payout dispatch runs behind a swappable `PayrollProvider` interface.
- **FR-PAY-02** — The default/fallback implementation exports approved payouts as a CSV for manual payroll processing. This alone constitutes a viable v1.
- **INT-01** — Provide a real `PayrollProvider` implementation for **Employment Hero** (public REST API; higher priority — more accessible).
- **INT-02** — Provide a real `PayrollProvider` implementation for **Workday** (tenant-gated / enterprise; lower priority). **DEFERRED** pending customer tenant access.
- **FR-PAY-03** — Payout dispatch is **idempotent**: a per-request idempotency key guarantees retries never double-pay (see `NFR-06`).

### 3.8 Authentication, authorization, organizations (`FR-AUTH`)
- **FR-AUTH-01** — Users authenticate to access the portal. Initial implementation may use email/password or a single SSO provider.
- **FR-AUTH-02** — Role-based access control (RBAC) enforces the `individual` / `employee` / `approver` / `admin` roles across all endpoints and views. Individual users have access only to individual-mode features; organization features are gated to org-affiliated roles.
- **FR-AUTH-03** — **DEFERRED:** Generic SSO/SAML via OIDC providers (Google, GitHub, Microsoft) and SAML, delivered through a provider such as WorkOS.
- **FR-AUTH-04** — **DEFERRED:** Multi-tenant organization model — every domain row is tenant-scoped, access is tenant-isolated, and users belong to one or more organizations.

### 3.9 Frontend portal (`FR-FE`)

**General (`FR-FE-GEN`)**
- **FR-FE-01** — A single responsive web portal serves all roles; layout and available navigation adapt to the authenticated user's role(s) and mode(s). Fully usable on mobile browsers.
- **FR-FE-02** — Delivered as a PWA: installable, with a mobile-optimized capture experience. Receipt capture uses the device camera via the file input `capture` attribute; no native app required.
- **FR-FE-03** — Global shell: top-level navigation (role-aware), authenticated user menu, and a persistent primary "Scan receipt" action that is reachable from anywhere.
- **FR-FE-04** — Every asynchronous operation (upload, extraction, categorization, synopsis, artifact generation) has an explicit UI state: pending/loading, success, and a recoverable error state with retry. No silent failures.
- **FR-FE-05** — All monetary values are displayed with currency and correct minor-unit formatting derived from the stored integer cents (never client-side float math).
- **FR-FE-06** — Accessibility baseline: keyboard-navigable, labeled controls, sufficient contrast; built on shadcn/ui primitives.

**Capture & confirmation (shared by both modes) (`FR-FE-CAP`)**
- **FR-FE-07** — Capture screen: camera/file capture, multi-receipt support, thumbnail previews, and re-capture/remove before processing.
- **FR-FE-08** — Processing screen: shows extraction/categorization progress per receipt, with skeleton placeholders while the async job runs.
- **FR-FE-09** — Review & confirm screen: renders the extracted breakdown as an editable table (description, amount, category per line item), plus merchant/date/total header. Inline editing of any field; category selection via dropdown constrained to the taxonomy.
- **FR-FE-10** — The review screen surfaces the reconciliation result (`FR-CONF-03`) visibly: a clear warning banner and highlighted rows when line-item sum ≠ extracted total, blocking silent confirmation.
- **FR-FE-11** — Low-confidence or `uncategorized` items (`FR-CAT-03`) are visually flagged to draw the user's attention before confirmation.

**Individual-mode views (`FR-FE-IND`)**
- **FR-FE-12** — Dashboard/home: spending overview with summary tiles (total this period, by top categories) and recent receipts.
- **FR-FE-13** — Spending report screen: filterable by date range, category, and merchant; grouped totals with a simple chart (e.g. spend by category) and a data table. Export controls for CSV/PDF (`FR-IND-03`).
- **FR-FE-14** — Item-selection screen: browse personal spending history and select specific line items (across receipts) to include in an outbound request; running total of the selection is shown.
- **FR-FE-15** — Request-composition screen: displays the generated synopsis and the editable outbound artifact (email subject/body or document preview), an external-payer field, and edit-before-finalize (`FR-IND-06`). Actions to download, copy, or (later) send.
- **FR-FE-16** — Request history: list of previously generated/sent outbound requests, each showing covered items and generation/sent timestamp (`FR-IND-08`).

**Organization-mode views (`FR-FE-ORG`)**
- **FR-FE-17** — Employee: request list with status badges (draft/submitted/approved/rejected/paid), request detail (receipt image + breakdown + synopsis), and submit action.
- **FR-FE-18** — Approver: pending-approval queue, request detail (receipt + breakdown + synopsis + submitter), and approve/reject with an optional note; self-approval is disallowed in the UI (`FR-WF-04`).
- **FR-FE-19** — Admin: category-taxonomy management, user/role management, and integration configuration (payroll provider, etc.).
- **FR-FE-20** — Request detail (both org roles) shows the human-readable audit trail (`FR-NOTE-02`).

### 3.10 Notifications & audit (`FR-NOTE`)
- **FR-NOTE-01** — Notify relevant users on key transitions (submitted → approver; approved/rejected → employee).
- **FR-NOTE-02** — Every request exposes a human-readable audit trail derived from the audit log.

---

## 4. Non-Functional Requirements

- **NFR-01 (Async-first)** — All slow, multi-step operations (OCR, categorization, synopsis) run as background jobs, not in the request/response cycle.
- **NFR-02 (Provider abstraction)** — OCR and payroll are integrated via interfaces with a default implementation, so alternates can be swapped without a rewrite.
- **NFR-03 (Contract-driven)** — The API is defined by a language-neutral contract (OpenAPI) from which the frontend client is generated, keeping the TS frontend and Python backend in sync across the language boundary.
- **NFR-04 (Immutable audit)** — Financial state changes are recorded in an append-only audit log capturing actor, action, timestamp, and the figures involved.
- **NFR-05 (Money integrity)** — Money is integer minor units + explicit currency, never floats.
- **NFR-06 (Idempotency)** — Externally-visible side effects (payouts) are idempotent under retry.
- **NFR-07 (Data privacy)** — Receipt data contains PII/financial data; handle storage, access, and third-party transmission accordingly. (This is the axis that would later justify a self-hosted OCR path.)
- **NFR-08 (Solo/part-time constraint)** — Favor managed services and minimal deploy surface; the build target is a single part-time developer using AI tooling.

---

## 5. Tech Stack (DECIDED)

**Split stack: TypeScript frontend + Python backend, in one polyglot monorepo.**

### Frontend
| Concern | Choice |
|---|---|
| Framework | Next.js (App Router) |
| Language | TypeScript |
| Styling | Tailwind CSS |
| Components | shadcn/ui |
| Delivery | Responsive / PWA; mobile camera via file input `capture` attribute |
| API client | Generated from backend OpenAPI spec |
| Role | Frontend + thin BFF/proxy only; **not** the primary backend |

### Backend
| Concern | Choice |
|---|---|
| Language | Python |
| Framework | FastAPI (async) |
| Validation / serialization | Pydantic v2 |
| ORM | SQLAlchemy 2.0 (async) |
| Migrations | Alembic |
| Background jobs / queue | ARQ (async-native, Redis-based) — *default*; Celery + Redis if a heavier system is later needed |
| Broker / cache | Redis |
| Package / env management | uv |
| Testing | pytest + httpx |
| API contract | FastAPI auto-generates OpenAPI → consumed by frontend codegen |

### Data, auth, integrations
| Concern | Choice |
|---|---|
| Database | PostgreSQL (managed: Supabase DB / Neon / host-managed) |
| Object storage | S3-compatible / Supabase Storage (receipt images) |
| OCR (default) | Cloud document service — AWS Textract `AnalyzeExpense` (via `boto3`) or Azure AI Document Intelligence (via Azure SDK), behind `OcrProvider` |
| OCR (deferred) | Self-hosted (PaddleOCR / docTR + OpenCV), same interface |
| Categorization & synopsis | LLM with structured/enumerated output |
| Auth / SSO | WorkOS (SSO/SAML/directory) — *deferred*; or `authlib` / `python3-saml` self-hosted |
| Authorization | Application-level RBAC; optionally Cerbos/Oso/Casbin later |

### Deployment topology
| Component | Host |
|---|---|
| Frontend | Vercel |
| Backend API | Container host (Fly.io / Railway / Render) |
| Worker (jobs) | Separate process on the container host |
| Redis | Managed Redis on the container host |
| Postgres | Managed Postgres |

> **Note:** This split stack carries more operational overhead than an all-TypeScript setup (separate deploy target + worker + broker + cross-language codegen). It is a deliberate choice, justified by developer fluency and/or future non-OCR ML ambitions (e.g. fraud/anomaly detection, spend analytics) — **not** by the current feature list, which TypeScript alone could satisfy.

---

## 6. Repository Layout (DECIDED: polyglot monorepo)

```
reimburst/
  apps/
    web/                # Next.js frontend (TS)
    api/                # FastAPI backend (Python)
    worker/             # ARQ worker process (Python; may share code with api)
  packages/
    contract/           # OpenAPI spec + generated TS client
    shared-ts/          # Shared TS types, category taxonomy (frontend side)
  py/
    shared/             # Shared Python domain code, Pydantic models, taxonomy
  turbo.json            # JS task orchestration
  pnpm-workspace.yaml
  pyproject.toml / uv    # Python workspace/tooling
```

Cross-language type safety is achieved via the **OpenAPI contract**, not shared imports: the backend emits the spec; the frontend generates its client from it.

---

## 7. Core Data Model (sketch)

- **organizations** — (deferred multi-tenancy anchor) `id`, `name`.
- **users** — `id`, `org_id` (**nullable** — null for individual-only users), `email`, `role` (`individual`/`employee`/`approver`/`admin`).
- **categories** — `id`, `org_id` (**nullable** — null denotes a system-default/global taxonomy usable by individual users), `name` (the fund taxonomy).
- **reimbursement_requests** — (organization mode) `id`, `org_id`, `employee_id`, `status` (state machine), `synopsis`, `currency`, timestamps.
- **receipts** — `id`, `owner_id` (the capturing user), `request_id` (**nullable** — null for individual-mode receipts not tied to an org request), `image_key`, `raw_extraction` (provider JSON), `merchant`, `date`, `total_cents`, `tax_cents`.
- **line_items** — `id`, `receipt_id`, `description`, `amount_cents`, `category_id`.
- **outbound_requests** — (individual mode) `id`, `user_id`, `synopsis`, `artifact` (email/document content), `external_payer`, `status` (`draft`/`generated`/`sent`), `created_at`, `sent_at`.
- **outbound_request_items** — join of `outbound_request_id` ↔ `line_item_id` (which items a given outbound request covers, per `FR-IND-08`).
- **payouts** — `id`, `request_id`, `provider`, `idempotency_key`, `status`.
- **audit_events** — append-only: `id`, `request_id`, `actor_id`, `action`, `payload`, `created_at`.

All monetary columns are integer cents. `status` and `role` are enums. Receipts are owned by a user and optionally linked to an organization request; this single receipt/line-item core serves both modes.

---

## 8. Sub-Projects & Timeline

**Assumptions:** solo developer, ~1–2 focused hours/day, AI-assisted. Estimates are honest-but-optimistic; third-party sandbox access and integration debugging carry the most variance. **Governing principle: build one thin vertical slice end-to-end before widening.**

| Phase | Name | Scope | Est. (part-time) |
|---|---|---|---|
| **P0** | Foundations | Monorepo, FastAPI + Next.js scaffold, Postgres schema, OpenAPI→TS codegen, CI, deployed "hello world" on both hosts | 1–2 weeks |
| **P1** | Core extraction | Receipt upload → object storage → async OCR job → structured breakdown persisted & displayed. `OcrProvider` (cloud default). *(`FR-OCR-*`)* | 2–3 weeks |
| **P2** | Categorization + editable confirmation | LLM categorization to taxonomy; editable review UI; reconciliation gate. *(`FR-CAT-*`, `FR-CONF-*`)* | 1–2 weeks |
| **P3** | Individual mode | Personal spending history, spending reports + CSV/PDF export, item selection, LLM synopsis + outbound request artifact (email/PDF) with edit/download. Self-contained; needs no approver or payroll. *(`FR-IND-*`, `FR-SYN-*`, `FR-FE-IND`)* | 2–3 weeks |
| **P4** | Org workflow | State machine, approver view, synopsis in org context, audit log on transitions. *(`FR-WF-*`, `FR-SYN-*`, `FR-FE-ORG`)* | 2–3 weeks |
| **P5** | Auth, RBAC, notifications, polish | Auth + role gating (individual vs org roles), notifications, audit trail view, error states. *(`FR-AUTH-01/02`, `FR-NOTE-*`)* | 1–2 weeks |
| **P6** | Payout & integration | `PayrollProvider` with CSV fallback first, then Employment Hero adapter (idempotent). *(`FR-PAY-*`, `INT-01`)* | 2–4 weeks (high variance) |
| **P7 (DEFERRED)** | Multi-tenant + SSO/SAML + Workday | Tenant scoping, WorkOS SSO, org management, Workday adapter. *(`FR-AUTH-03/04`, `INT-02`)* | — |

**Realistic target: ~4–5 months part-time to a usable MVP.** Note the sequencing advantage: after P3, **individual mode is a complete, shippable product on its own** (scan → categorize → report → generate request) with no dependency on the organization workflow or payroll — a natural first release and de-risking milestone. Organization mode (P4–P6) then builds on the same pipeline.

**Cross-cutting invariants (built in from P0, not retrofitted):** money-as-cents, reconciliation gate, immutable audit log, idempotent payouts, provider interfaces for OCR and payroll.

---

## 9. First Step (in detail)

**Goal of step one: validate the riskiest assumption before building architecture.** The entire product depends on receipt extraction being reliable; prove it cheaply first.

### Step 1a — OCR validation spike (throwaway)
1. Collect **5–10 real, messy receipts**: faded, crumpled, non-English, handwritten totals, multi-column, unusual merchants.
2. Write a **single throwaway Python script** (no framework, no repo structure yet) that:
   - Reads one receipt image.
   - Calls the chosen cloud provider (`boto3` Textract `AnalyzeExpense`, or Azure Document Intelligence prebuilt-receipt).
   - Prints the returned structured fields: merchant, date, total, tax, and line items.
3. Run it across all sample receipts and record: extraction accuracy on amounts, correctness of line-item splitting, and total-vs-sum reconciliation behaviour.
4. **Decision output:** confirm the cloud provider is accurate enough for standard receipts (expected: yes). This validates `FR-OCR-04` and the reconciliation design (`FR-CONF-03`) before any real code exists. If accuracy is poor on your real receipts, this is the moment to reconsider provider or scope — cheaply.

### Step 1b — Monorepo scaffold (after the spike passes)
1. Initialize the polyglot monorepo per §6: `pnpm` + Turborepo for JS, `uv` for Python.
2. Scaffold `apps/api` with FastAPI and a `/health` endpoint; confirm it emits an OpenAPI schema.
3. Scaffold `apps/web` with Next.js + Tailwind + shadcn/ui; render a placeholder page.
4. Set up `packages/contract`: generate a TS client from the FastAPI OpenAPI schema and call `/health` from the frontend — proving the cross-language contract loop works.
5. Provision Postgres and define the §7 schema with SQLAlchemy + an initial Alembic migration.
6. Wire CI on GitHub; connect Vercel (web) and the container host (api + worker + Redis); **deploy both "hello world" targets now**, while stakes are zero.

### Definition of done for the first step
- The spike confirms cloud OCR returns usable structured receipt data on real samples.
- Both apps are deployed and reachable; the frontend successfully calls the backend via the generated client.
- The database schema exists behind a versioned migration.

**What comes next (P1):** replace the placeholder with the real vertical slice — upload → store → async extraction job → displayed breakdown — for a single user with no auth. That milestone proves the product's core loop end-to-end.

---

## 10. Out of Scope (current phase)

- Multi-tenant isolation and organization management (`FR-AUTH-04`) — architected for, not built.
- Generic SSO/SAML (`FR-AUTH-03`).
- Workday integration (`INT-02`).
- Self-hosted OCR/CV (`FR-OCR-04` alternate).
- Non-OCR ML features (fraud/anomaly detection, spend analytics) — the latent justification for the Python backend, but not a current requirement.
