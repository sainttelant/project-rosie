# Architecture & End-to-End Runtime Flow

*Canonical engineering reference for Project Rosie. This document describes the system **as the code currently stands** — every file path, endpoint, and stage callback below was verified against the source. It complements the narrated, biology-focused explainers in `docs/explainers/` and `docs/hackathon-writeup.md`. Where an older explainer and this document disagree, this document reflects the live code.*

> English version. 中文版见 [`architecture-and-flow.zh.md`](./architecture-and-flow.zh.md).

---

## TL;DR

Project Rosie is an **AI clinical assistant for oncologists, starting with veterinary medicine**. A user uploads a **VEP-annotated tumor VCF** (a spreadsheet of somatic mutations found in a cancer biopsy); the system produces, in under an hour and for a few dollars of compute:

1. A **ranked list of neoantigen vaccine targets** (top 20 candidates, scored)
2. A **synthesis-ready, codon-optimized mRNA vaccine sequence** (FASTA)
3. A **plain-language clinical report** (written by Gemma 4, reading the data *and* two charts)
4. A **CMO-grade mRNA synthesis specification** (deterministic Jinja template — not LLM-generated)
5. Two **diagnostic charts** (binding-affinity bar chart, mutation-landscape pie chart)

### The three runtimes

| Subsystem | Runtime | Location |
|---|---|---|
| Web app + API | Node.js — Next.js 16 App Router (deployed on Vercel) | `src/` |
| Bioinformatics pipeline | Python (pVACtools, NetMHCpan, Biopython, pandas) in a Docker image on **Cloud Run Jobs** | `pipeline/` |
| Intelligence layer | **Gemma 4** via Vertex AI — called from *both* subsystems | — |
| State + auth | Supabase (PostgreSQL + Row-Level Security + Realtime) | `supabase/` |
| File storage | Google Cloud Storage (VCF uploads, 30-day lifecycle) | — |

### The one rule that organizes everything

> **Deterministic code does the biology; Gemma does the interpretation.**

The scoring, mRNA design, and synthesis spec are transparent, auditable Python + a template. Gemma is used only where reasoning is the point: advising *before* the expensive run, writing the report *after* it, narrating interactive "what-if" threshold changes, and answering free-form questions. Nothing the model says changes the ranked candidates or the mRNA sequence.

---

## What the system produces, and where it lands

| Output | Producer | Stored as | Surfaced by |
|---|---|---|---|
| Ranked candidates (top 20) | `pipeline/modules/scoring.py` | `cases.candidates_json` (JSONB) | `CandidatesTable`, `SensitivityPanel` |
| Binding-affinity bar chart (PNG) | `pipeline/modules/visualizations.py` | `cases.binding_affinity_img_b64` | `ReportViewer` |
| Mutation-landscape pie chart (PNG) | `pipeline/modules/visualizations.py` | `cases.mutation_landscape_img_b64` | `ReportViewer` |
| Clinical report (Markdown) | `pipeline/modules/gemma.py` (Gemma 4) | `cases.clinical_report_md` | `ReportViewer`, print/PDF via `/api/cases/[id]/download` |
| mRNA construct (FASTA) | `pipeline/modules/mrna_design.py` | `cases.mrna_fasta` | `MRNAViewer`, `.fasta` download |
| Synthesis spec (Markdown) | `pipeline/modules/synthesis_spec.py` (Jinja) | `cases.mrna_summary_md` | `ReportViewer`, print/PDF download |
| Summary stats | `pipeline/modules/scoring.py` | `cases.total_mutations`, `cases.candidates_after_filtering` | timeline, dashboard |

---

## Repository map

```
project-rosie/
├── src/                          # Next.js 16 app (frontend + API routes), TypeScript
│   ├── app/
│   │   ├── (app)/                # Auth-gated clinic area
│   │   │   ├── dashboard/        # Case list (GET /api/cases)
│   │   │   ├── submit/           # New case: VCF upload + advisor + submit
│   │   │   └── cases/[id]/       # Live status timeline + report + chat + sensitivity
│   │   ├── (public)/             # overview, docs, writeup, architecture, demo pages
│   │   ├── auth/                 # login / signup / callback (Supabase auth)
│   │   └── api/                  # API routes (see "API routes" table below)
│   ├── components/               # PipelineTimeline, ReportViewer, ChatWidget,
│   │   │                         # VcfAdvisor, SensitivityPanel, CandidatesTable, …
│   │   └── ui/                   # shadcn-style primitives
│   ├── lib/
│   │   ├── gcp-auth.ts           # GCP token: JSON key / WIF-OIDC / ADC fallback
│   │   ├── vcf-stats.ts          # Browser-side VCF structural parser (for VcfAdvisor)
│   │   ├── sensitivity.ts        # Client-side what-if re-rank (mirrors scoring.py)
│   │   ├── supabase/{client,server}.ts   # @supabase/ssr (browser + server + admin)
│   │   └── utils.ts
│   ├── types/case.ts             # Shared TS types (Candidate, CandidatesJson, …)
│   └── proxy.ts                  # Next.js middleware/proxy hook
├── pipeline/                     # Python bioinformatics pipeline (Cloud Run Jobs target)
│   ├── run_cloud.py              # Cloud Run entrypoint — env-configured, POSTs callbacks
│   ├── run_pipeline.py           # Local CLI entrypoint (same stages, no cloud)
│   ├── Dockerfile                # FROM griffithlab/pvactools + NetMHCpan 4.2 + deps
│   ├── modules/
│   │   ├── prediction.py         # wraps `pvacseq run`
│   │   ├── scoring.py            # hard filters + composite ranking → candidates JSON
│   │   ├── visualizations.py     # two matplotlib PNGs
│   │   ├── gemma.py              # Gemma 4 multimodal clinical report
│   │   ├── mrna_design.py        # codon-optimized multi-epitope mRNA → FASTA
│   │   ├── synthesis_spec.py     # Jinja CMO synthesis spec
│   │   ├── annotation.py         # VEP via Docker (local / canine pre-processing)
│   │   └── __init__.py
│   ├── templates/synthesis_spec.md.j2
│   ├── vep_plugins/{Wildtype.pm,Frameshift.pm}
│   ├── scripts/{build_demo.py,wipe_and_seed_demo.py}
│   └── requirements.txt
├── supabase/
│   ├── config.toml
│   └── migrations/20260508000001_cases.sql   # `cases` table + RLS + Realtime
├── scripts/
│   ├── gcs-lifecycle.json        # 30-day auto-delete on pipeline work files
│   └── seed_demo.py              # seed the public demo case (user_id IS NULL)
├── .github/workflows/supabase-keepalive.yml
├── docs/                         # this file + explainers + blog + writeup
└── README.md
```

---

## Architecture at a glance

```
                        ┌──────────────────────────────────────────────┐
                        │                BROWSER (Vercel)              │
   Supabase Realtime ◄──┤  submit → cases/[id] timeline → report/chat  │
   (WebSocket push)     └───────┬───────────────────────────┬──────────┘
                                │  POST /api/cases          │ POST /api/cases/{id}/chat
                                ▼                          │ /sensitivity-narrate
                        ┌───────────────────┐              │ /api/vcf-advisor
                        │ Next.js API (Node)│──────────────┤
                        │  auth: Supabase   │   GCP token  │   (Gemma 4 via Vertex AI)
                        └───┬─────────┬─────┘              │
        POST /api/upload    │         │ triggerJob         │
        (multipart→GCS)     ▼         ▼                    ▼
                ┌──────────────┐   ┌────────────────────────────────────┐
                │  GCS bucket  │   │   Cloud Run Job (Docker container) │
                │  (VCF files) │   │   ENTRYPOINT: python run_cloud.py  │
                └──────┬───────┘   │  ┌──────────┬────────┬───────────┐ │
                   read│          │  │prediction│ scoring│  visualiz.│ │
                       └──────────►│  │ (pVACseq)│ (rank)│   (charts)│ │
                                   │  └──────────┴────────┴───────────┘ │
                                   │  ┌────────────┬──────────────────┐ │
                                   │  │ gemma.py   │ mrna_design +    │ │
                                   │  │(clinical   │ synthesis_spec   │ │
                                   │  │  report)   │  (FASTA/CMO doc) │ │
                                   │  └────────────┴──────────────────┘ │
                                   └──────────────────┬─────────────────┘
                                                      │ POST /api/cases/{id}/progress
                                                      │ Authorization: Bearer PIPELINE_CALLBACK_SECRET
                                                      ▼
                        ┌──────────────────────────────────────────────────┐
                        │   Supabase (Postgres) — `cases` table (RLS)     │
                        │   every stage update → Realtime push → browser  │
                        └──────────────────────────────────────────────────┘
```

---

## End-to-end runtime flow

The full journey of one submission, phase by phase. File paths are the exact code that executes.

### Phase 0 — Authentication

Supabase auth (email + OTP, wired via `@supabase/ssr`). Server routes read the cookie through `src/lib/supabase/server.ts` → `supabase.auth.getUser()`. A user id is attached to every `cases` row, and Row-Level Security (see "Data model") enforces that a user can only touch their own rows. Public **demo** rows have `user_id IS NULL` and are readable without auth (used by `/demo` and by the chat/sensitivity routes, which branch on `user_id IS NULL`).

### Phase 1 — Submit: upload the VCF

Code: `src/app/(app)/submit/page.tsx` → `handleSubmit()`.

1. User enters **sample name**, picks **species** (defaults to `canis_lupus_familiaris`), and confirms **MHC/DLA alleles** (preset per species).
2. On file select, `VcfAdvisor` runs **before** submission (Gemma 4 Role 1 — see below): `src/lib/vcf-stats.ts` parses the first ~5 MB client-side to extract structural facts (variant count, INFO keys, TUMOR/NORMAL columns, somatic flags, chromosomes, FILTER values); `POST /api/vcf-advisor` returns 0–3 advisory notes. **It never blocks submission** — on any failure it degrades to `{ notes: [] }`. The route also hard-checks for a `CSQ` INFO key (pVACseq requires VEP annotation) deterministically, before spending a Gemma call.
3. **Upload**: `POST /api/upload` (`src/app/api/upload/route.ts`) receives the file as `multipart/form-data`, and streams it to GCS with `uploadType=media` under `vcf/{user.id}/{timestamp}/{filename}`. Returns `gcsPath` as `gs://bucket/...`.
   > **Note on the live upload path.** The submit page uses `POST /api/upload` (file passes *through* Next.js). A second route, `GET /api/upload-url` (`uploadType=resumable`, browser→GCS direct), also exists but is **not** what the current submit page calls. `docs/explainers/04-cloud-deployment.md` describes the resumable path as the live one — that is the stale bit.
4. **Create case**: `POST /api/cases` (`src/app/api/cases/route.ts`) with `{ sample_name, species, alleles, gcs_vcf_path }`.
   - Enforces the **10-submission cap** (returns `429`).
   - Inserts a `cases` row with `status: "running"`.
   - Calls `triggerPipelineJob()` → `POST https://run.googleapis.com/v2/projects/{project}/locations/{region}/jobs/{job}:run`, injecting per-run env (`CASE_ID`, `GCS_VCF_PATH`, `SAMPLE_NAME`, `ALLELES`, `SPECIES`, `CALLBACK_URL`, `PIPELINE_CALLBACK_SECRET`, `GCS_BUCKET`, `GCP_PROJECT_ID`, `GEMMA_MODEL`).
   - Awaits the trigger; if it fails, marks the row `failed` and returns `500`.
   - Returns `{ id }` with `201`.
5. Browser navigates to `/cases/{id}`.

### Phase 2 — Live status tracking

`/cases/{id}/page.tsx` (client) + `PipelineTimeline` subscribe to the Supabase Realtime channel on `cases` (added to `supabase_realtime` in the migration). Every time the pipeline POSTs a stage update, the row changes, Supabase pushes it over WebSocket, and the UI re-renders the timeline — **no polling, no refresh**.

### Phase 3 — Cloud Run pipeline (`pipeline/run_cloud.py`)

All config arrives via environment variables. The job:

1. `callback("running")`.
2. Download the VCF from GCS into a temp dir.
3. **Stage 1 — Prediction** (`modules/prediction.py:run_pvacseq`): runs
   `pvacseq run <vcf> <vcf-sample-id> <alleles> <algo> <out> -e1 8,9,10,11 -m median -b 500 -c 1`.
   It reads the *actual* sample column from the VCF `#CHROM` header (the user's display name won't match). Output: `MHC_Class_I/{sample}.MHC_I.all_epitopes.tsv`.
   > Optional `SKIP_PREDICTION=true` path loads a pre-computed TSV from `GCS_TSV_PATH` instead.
4. **Stage 2 — Scoring** (`modules/scoring.py:score_candidates`): hard filters (`IC50 ≤ 500 nM`, `Tumor VAF ≥ 0.01`), then composite score `0.50·IC50 + 0.30·immunogenicity + 0.20·VAF`, keep **top 20** → candidates JSON. `callback("scoring")` is sent before, and again after (carrying `total_mutations` + `candidates_after_filtering`).
5. **Stage 3 — Visualizations** (`modules/visualizations.py:generate_all`): matplotlib (headless `Agg`) → binding-affinity bar chart + mutation-landscape pie chart (two PNGs). `callback("reporting")`.
6. **Stage 4 — Clinical report** (`modules/gemma.py:generate_clinical_report`): Gemma 4 (Vertex AI) reads the candidates JSON **and** both PNGs (multimodal) under a species-aware system prompt, writes a 400–600 word report; `_embed_images` then injects the chart references.
7. **Stage 5 — mRNA design** (`modules/mrna_design.py:design_mrna`): top 3 epitopes joined with `AAY` linkers, wrapped in `5'UTR → Kozak+ATG → CDS → 3'UTR → poly-A(60)`, codon-optimized with the highest-frequency canine codon per amino acid → FASTA + a Markdown design summary. `callback("designing")`.
8. **Stage 5b — Synthesis spec** (`modules/synthesis_spec.py:generate_synthesis_spec`): renders `templates/synthesis_spec.md.j2` (Jinja) into a CMO-grade order document. **Non-fatal** — on error it falls back to the design summary.
9. **Final**: `callback("completed", candidates_json, clinical_report_md, mrna_fasta, mrna_summary_md, binding_affinity_img_b64, mutation_landscape_img_b64)`.

Any stage throwing → `callback("failed", error_message=...)` and `sys.exit(1)`.

**Stage → `cases.status` mapping:**

| Pipeline point | `status` value |
|---|---|
| Job start | `running` |
| Scoring (before + after) | `scoring` |
| Visualizations + report | `reporting` |
| mRNA design | `designing` |
| All done | `completed` |
| Any exception | `failed` |

> The `callback()` helper retries `completed`/`failed` up to 4× (they must land or the case is stuck forever); non-critical updates are best-effort (1 attempt). If a critical callback can't be delivered it exits non-zero so Cloud Run records the failure.

### Phase 4 — Callback into the database

`POST /api/cases/[id]/progress` (`src/app/api/cases/[id]/progress/route.ts`):

- Verifies `Authorization: Bearer {PIPELINE_CALLBACK_SECRET}` (shared secret, **not** user auth).
- Uses the **admin/service-role** client (`createAdminClient`) so it bypasses RLS and can write the row.
- Merges any subset of `status`, stats, `candidates_json`, `clinical_report_md`, `mrna_fasta`, `mrna_summary_md`, both base64 images, and `error_message`, and stamps `updated_at`.

Because this update happens on the `cases` table, **Supabase Realtime fans it out to the browser** (Phase 2). When `status` reaches `completed`, the report viewer, mRNA viewer, and charts render from the row.

### Phase 5 — Reading results & acting on them

On `/cases/{id}` (and the public `/demo`):

- **`ReportViewer`** renders the clinical report Markdown (with the two charts) and offers print/PDF.
- **`MRNAViewer`** renders the codon-optimized mRNA construct.
- **`CandidatesTable`** shows the ranked top candidates.
- **`SensitivityPanel`** (`src/lib/sensitivity.ts`) re-ranks candidates **client-side** as the user drags IC50/VAF sliders (zero LLM cost); on demand it calls `POST /api/cases/[id]/sensitivity-narrate` for a 1–2 sentence Gemma 4 interpretation.
- **`ChatWidget`** → `POST /api/cases/[id]/chat` for free-form Q&A grounded in the case's candidates + report.
- **Download** → `GET /api/cases/[id]/download?type=report-pdf|fasta|synthesis-pdf`:
  - `report-pdf` / `synthesis-pdf` return a styled, print-oriented HTML document (auto-`window.print()`) with images inlined as base64 data URIs.
  - `fasta` returns the mRNA FASTA as a file attachment.

### API routes, at a glance

| Route | Method | Auth | Purpose |
|---|---|---|---|
| `/api/cases` | GET, POST | user (cookie) | List my cases; create a case + trigger Cloud Run |
| `/api/cases/[id]` | GET, DELETE | user | Fetch one case; delete it |
| `/api/cases/[id]/progress` | POST | shared secret | Pipeline stage callback → writes `cases` row |
| `/api/cases/[id]/chat` | POST | user *or* demo | Gemma 4 Q&A about the case |
| `/api/cases/[id]/sensitivity-narrate` | POST | user *or* demo | Gemma 4 narrative for what-if thresholds |
| `/api/cases/[id]/download` | GET | user | report-pdf / fasta / synthesis-pdf |
| `/api/upload` | POST | user | Multipart VCF → GCS (live path) |
| `/api/upload-url` | GET | user | GCS resumable-upload URI (alternative) |
| `/api/vcf-advisor` | POST | user | Gemma 4 pre-flight VCF review |
| `/auth/callback`, `/auth/login`, `/auth/signup` | — | — | Supabase auth |

---

## Gemma 4 — the four active roles

Gemma 4 (`gemma-4-26b-a4b-it-maas` by default) is only ever used to *interpret* or *advise* — never to compute a score or a sequence. Each role has the same shape: **pure lib → API route (auth + Gemma + safe-parse) → component**, degrading gracefully when the model is unavailable.

| # | Role | When | Code | Output |
|---|---|---|---|---|
| 1 | **Pre-flight VCF advisor** | On file select, before submit | `src/lib/vcf-stats.ts` → `src/app/api/vcf-advisor/route.ts` → `VcfAdvisor.tsx` | 0–3 structured advisory notes (JSON). Deterministic `CSQ` check first; Gemma for the rest. Never blocks. |
| 2 | **Multimodal clinical-report writer** | In-pipeline, after scoring/charts | `pipeline/modules/gemma.py` | 400–600 word plain-language report (reads JSON + 2 PNGs). |
| 3 | **Sensitivity narrator** | On demand, in the results view | `src/lib/sensitivity.ts` → `src/app/api/cases/[id]/sensitivity-narrate/route.ts` → `SensitivityPanel.tsx` | 1–2 sentence narrative on what a what-if threshold change costs/gains. |
| 4 | **Conversational assistant** | On demand, in the results view | `src/app/api/cases/[id]/chat/route.ts` → `ChatWidget.tsx` | Free-form answers grounded in this case's candidates + report. |

Roles 1–4 use the model via two different SDKs but the same Vertex AI model: **Python `google.genai`** in the pipeline (`gemma.py`), and **`@google/genai` (`GoogleGenAI`)** in the Node API routes.

---

## Data model

Everything in one table: `cases` (defined in `supabase/migrations/20260508000001_cases.sql`).

```
cases
├── id                         UUID PK, gen_random_uuid()
├── created_at / updated_at    TIMESTAMPTZ
├── user_id                    UUID → auth.users, ON DELETE CASCADE   (NULL = public demo case)
├── sample_name                TEXT
├── species                    TEXT  (default 'canis_lupus_familiaris')
├── alleles                    TEXT[]
├── predictors                 TEXT[] (default {NetMHCpan})
├── status                     TEXT  CHECK IN ('pending','running','scoring',
│                                                        'reporting','designing','completed','failed')
│   ── pipeline outputs (written by the /progress callback) ──
├── candidates_json            JSONB
├── clinical_report_md         TEXT
├── mrna_fasta                 TEXT
├── mrna_summary_md            TEXT
├── binding_affinity_img_b64   TEXT   (base64 PNG)
├── mutation_landscape_img_b64 TEXT   (base64 PNG)
│   ── summary stats ──
├── total_mutations            INTEGER
├── candidates_after_filtering INTEGER
└── error_message              TEXT
```

**Row-Level Security** (two policies):

```sql
CREATE POLICY "users_own_cases" ON cases FOR ALL
  USING (auth.uid() = user_id);
CREATE POLICY "demo_cases_public" ON cases FOR SELECT
  USING (user_id IS NULL);
```

So the API routes don't have to hand-filter by `user_id` for reads; the `/progress` callback is the one place that writes as the **service-role admin client** (bypasses RLS) after the shared-secret check.

**Design notes** (carried over from `docs/explainers/03-frontend-architecture.md`):
- Charts are stored as **base64 in Postgres** (small enough), not as GCS URLs — one-line change later if that becomes a problem.
- `candidates_json` is **JSONB** because it is always read whole (never queried per-candidate).
- The `status` column is the **single source of truth** that drives the client timeline via Realtime.

---

## GCP authentication

`src/lib/gcp-auth.ts` → `getGcpAccessToken()` returns a GCP access token for the Vercel API to call GCS + Cloud Run Jobs. Three paths, tried in order:

1. **`GOOGLE_APPLICATION_CREDENTIALS_JSON`** — service-account key. This is the **active production path** (short-circuits the others) because WIF hit reliability issues during the hackathon window.
2. **Workload Identity Federation** — exchange `VERCEL_OIDC_TOKEN` via STS for a federated token, then impersonate `rosie-pipeline-sa`. Correctly wired (project number `575738151193`, pool `vercel-pool`), currently the *intended* posture, not the live one.
3. **Application Default Credentials** — local dev fallback.

The pipeline (Cloud Run) authenticates to GCP by ambient service account; it reads the VCF from GCS and writes results back via the callback — it does not call the GCS upload path.

## Environment variables

| Variable | Set on | Purpose |
|---|---|---|
| `GCS_BUCKET` | Vercel + Cloud Run | Bucket for VCF uploads |
| `GCP_PROJECT_ID` / `GCP_REGION` | Vercel + Cloud Run | GCP project / region |
| `CLOUD_RUN_JOB_NAME` | Vercel | Job name (short or full resource path) |
| `PIPELINE_CALLBACK_SECRET` | Vercel + Cloud Run | Shared secret for the `/progress` callback |
| `NEXT_PUBLIC_APP_URL` | Vercel | Callback base URL passed into the job |
| `GEMMA_MODEL` | Vercel + Cloud Run | Vertex AI model id (default `gemma-4-26b-a4b-it-maas`) |
| `GOOGLE_APPLICATION_CREDENTIALS_JSON` | Vercel | Service-account key (active prod auth) |
| `VERCEL_OIDC_TOKEN` | auto (Vercel) | OIDC token for the WIF path |
| `CASE_ID`, `GCS_VCF_PATH`, `SAMPLE_NAME`, `ALLELES`, `SPECIES`, `GCS_TSV_PATH`, `SKIP_PREDICTION` | injected per-run by the Jobs API | Per-job config for `run_cloud.py` |

## The demo case

`scripts/seed_demo.py` (and `pipeline/scripts/{build_demo.py,wipe_and_seed_demo.py}`) seed a **public demo case** (`user_id IS NULL`) that powers `/demo`. Because RLS has `demo_cases_public`, and the chat/sensitivity routes branch on `user_id IS NULL`, the demo is fully explorable without an account.

## Known-stale spots in the older docs (fixed by this document)

- **`docs/explainers/01-...` (Steps 8 & 9)** says the Gemma report and mRNA design are *"not yet built."* Both are shipped: `pipeline/modules/gemma.py` and `pipeline/modules/mrna_design.py`.
- **`docs/explainers/04-cloud-deployment.md`** describes `GET /api/upload-url` (resumable) as the live upload path. The submit page actually calls `POST /api/upload` (multipart through Next.js). Both routes exist; `/api/upload` is the live one.
- The `README.md` "Four Active Roles" narrative and the data model are consistent with this document.

## Where to go next (phase-2, per `README.md`)

FASTQ ingestion (BWA-MEM2 + GATK Mutect2), MHC-II, peptide-MHC structure prediction (e.g. AlphaFold), PyClone-VI clonality, Nextflow orchestration, structure-aware codon optimization (LinearDesign), and multi-construct prime/boost dosing.

## Cross-references

- `docs/explainers/01-from-dna-to-vaccine-candidates.md` — plain-English biology walk-through + glossary
- `docs/explainers/02-key-decisions.md` — rationale for the major design choices
- `docs/explainers/03-frontend-architecture.md` — frontend, data model, and advisor-component wiring
- `docs/explainers/04-cloud-deployment.md` — GCS, Cloud Run Jobs, WIF, callbacks
- `docs/hackathon-writeup.md` — Gemma4Good submission narrative
- `README.md` — product overview and the four Gemma roles
