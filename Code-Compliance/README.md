# Building Energy Code & Standards Assistant

A conversational RAG assistant grounded in the Canadian **National Energy Code for
Buildings (NECB)** and, by design, any additional codes/standards you add to the
knowledge base.

## Architecture at a glance

```
┌────────────┐      ┌──────────────────┐      ┌─────────────────────┐
│  Frontend  │─────▶│  API Gateway     │─────▶│  ALB (private)      │
│  (Amplify) │      │  (public HTTPS)  │      │  ── ECS EC2 task    │
└────────────┘      └──────────────────┘      │     FastAPI + FAISS │
                                              └──────────┬──────────┘
                                                         │
                                          ┌──────────────┴──────────────┐
                                          ▼                             ▼
                                   ┌────────────┐               ┌──────────────┐
                                   │  Bedrock   │               │  S3 bucket   │
                                   │  (Titan +  │               │  kb/<code>/  │
                                   │   Nova Pro)│               │  index.faiss │
                                   └────────────┘               └──────────────┘
```

- **Retrieval:** self-managed FAISS (`faiss-cpu`) — inner-product over L2-normalised
   Titan embeddings combined with BM25 keyword rankings using reciprocal-rank fusion.
   Explicit table numbers are prioritized; table requests favor structured tables,
   and matching row chunks are expanded to their full table to retain column headers.
   Retrieval scores are ranking scores, not confidence probabilities.
   Indexes are pre-built offline (per code) and uploaded to S3.
  On boot, the ECS task downloads the bundles and loads them into memory.
- **Generation:** AWS Bedrock `Converse`/`ConverseStream`. Default model is
  `mistral.mistral-large-2402-v1:0` (strongest LLM with confirmed access in
  `ca-central-1` for this account); swap by changing the `BEDROCK_MODEL_ID` env
  var (no rebuild needed).
- **Auth:** shared Cognito user pool with the other CanBuildAI services (same
  `Authorization: Bearer <idToken>` pattern).

## Layout

```
Code-Compliance/
├── data/                          # source PDFs (NECB2020.pdf, NECB2025.pdf, …)
├── knowledge_bases.json           # registry: which codes exist, which are enabled
├── indexes/                       # local build output (git-ignored)
├── requirements.txt               # deps for OFFLINE ingestion
└── src/
    ├── ingestion/
    │   ├── pdf_chunker.py         # PDF → chunks (with section + page metadata)
    │   ├── embed_and_index.py     # Titan embeddings + FAISS bundle writer + S3 upload
    │   └── build_index.py         # CLI entrypoint (`python -m src.ingestion.build_index`)
    └── retriever/
        ├── faiss_store.py         # in-memory multi-code FAISS store used by the API
        └── s3_sync.py             # downloads bundles from S3 at container startup
```

At container build time, `Dockerfile.code-assistant` copies `Code-Compliance/src`
into `/home/btap_ml/code_compliance` so the FastAPI service (in
`surrogate-app/src/api/services/bedrock_rag.py`) imports it as
`code_compliance.retriever.*`.

## Adding a new code / standard

1. Drop the PDF in `data/` (e.g. `ASHRAE-90.1-2022.pdf`).
2. Add an entry to [`knowledge_bases.json`](./knowledge_bases.json):
   ```json
   {
     "id": "ashrae_90_1_2022",
     "label": "ASHRAE 90.1-2022",
     "long_name": "ASHRAE Standard 90.1-2022 Energy Standard for Buildings",
     "pdf": "ASHRAE-90.1-2022.pdf",
     "language": "en",
     "jurisdiction": "US/International",
     "enabled": true,
     "default_selected": false
   }
   ```
3. Rebuild + upload just that code:
   ```powershell
   cd surrogate-app\Code-Compliance
   .\.venv\Scripts\Activate.ps1
   $env:CODE_ASSISTANT_KB_BUCKET = "btap-code-assistant-dev-kb"
   $env:AWS_PROFILE = "dev"
   python -m src.ingestion.build_index --only ashrae_90_1_2022 --upload
   ```
4. Restart the ECS service (force new deployment) — the container downloads the
   new bundle on next boot and it appears automatically in the frontend chip
   list.

## Building the initial NECB indexes

```powershell
cd surrogate-app\Code-Compliance
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Dry run first — chunks only, no Bedrock calls (verifies PDFs parse cleanly).
python -m src.ingestion.build_index --no-embed

# Real build (requires AWS creds with Bedrock InvokeModel permission).
$env:AWS_PROFILE = "dev"
python -m src.ingestion.build_index

# Upload to the S3 bucket created by Terraform.
$env:CODE_ASSISTANT_KB_BUCKET = "btap-code-assistant-dev-kb"
python -m src.ingestion.build_index --upload
```

## Deployment (first-time)

The pattern mirrors the surrogate and retrofit modules:

1. **Infra:**
   ```powershell
   cd api-infrastructure\code_assistant_infrastructure\infrastructure\live\dev
   terragrunt apply
   ```
   Note the outputs: `application_url`, `kb_bucket_name`, `ecs_cluster_name`,
   `ecs_service_name`, `ecs_task_family`.

2. **Build & upload FAISS indexes** to the `kb_bucket_name` (see above).

3. **GitHub Actions secrets** (per repo, one-time):
   - `CODE_ASSISTANT_ECS_CLUSTER`   → `ecs_cluster_name` output
   - `CODE_ASSISTANT_ECS_SERVICE`   → `ecs_service_name` output
   - `CODE_ASSISTANT_ECS_TASK_FAMILY` → `ecs_task_family` output
   - `CODE_ASSISTANT_APP_BASE_URL`  → `application_url` output
   - `CODE_ASSISTANT_KB_BUCKET`     → `kb_bucket_name` output
   - `BEDROCK_MODEL_ID`             → e.g. `mistral.mistral-large-2402-v1:0`
   - `BEDROCK_EMBED_MODEL_ID`       → `amazon.titan-embed-text-v2:0`
   - `BEDROCK_EMBED_DIM`            → `1024`
   - `BEDROCK_REGION`               → `ca-central-1`

   (Cognito + Docker Hub + AWS role secrets are reused from the surrogate/retrofit
   configuration.)

4. **First release:**
   ```powershell
   cd surrogate-app
   git tag code-assistant-v1.0.0
   git push origin code-assistant-v1.0.0
   ```
   The `deploy-code-assistant.yml` workflow builds the image and rolls the ECS
   service.

5. **Frontend:** set `window.CODE_ASSISTANT_API_URL` in `code-assistant.html`
   (or replace the placeholder near the top of its `<script>` block) with the
   Terraform `application_url` output, then push to Amplify.

## Swapping the LLM

Change `BEDROCK_MODEL_ID` in **either**:

- the GitHub secret (re-run the workflow to push a new task definition), OR
- the `bedrock_model_id` input in `infrastructure/live/dev/terragrunt.hcl` and
  `terragrunt apply`.

Verified accessible on-demand in `ca-central-1` (account 834599497928):

| Model ID | Notes |
|---|---|
| `mistral.mistral-large-2402-v1:0` | **Default** — strongest instruction-following, cleanest Converse output, excellent EN/FR |
| `meta.llama3-70b-instruct-v1:0` | Strong reasoning; may bleed chat-template tokens (add `stopSequences` if needed) |
| `mistral.mixtral-8x7b-instruct-v0:1` | Mid-tier fallback |
| `meta.llama3-8b-instruct-v1:0` | Fast / cheap fallback |
| `mistral.mistral-7b-instruct-v0:2` | Smallest fallback |

**Model access check (2026-10-01):** the running ECS service still uses
Mistral Large. A direct Claude 3 Sonnet invocation in `ca-central-1` was denied
because of private Marketplace eligibility. `ca.amazon.nova-lite-v1:0` exists
and routes only to `ca-central-1` and `ca-west-1`, but invocation was denied by
an organization SCP on its `ca-west-1` model resource. Newer Claude and OpenAI
models are listed through US/global profiles. US inference has been approved by
the project owner, but test invocations of `us.anthropic.claude-sonnet-4-6`,
`us.anthropic.claude-opus-4-6-v1`, and `us.openai.gpt-5.4` were explicitly denied
by organization SCP `p-m9mnbpri` on their `us-east-1` model resources. An AWS
organization administrator must resolve the applicable policy restriction before
switching to these profiles; Marketplace eligibility may also need approval.
US routing sends user questions and conversation context as well as retrieved
public code excerpts outside Canada. Catalog `ACTIVE` status is not proof of
invocation access. No stronger replacement has passed an invocation test yet.

The table-retrieval fix requires an application image rebuild/deployment, not an
index rebuild, when bundles already contain `table` and `table_row` metadata.
Both deployed NECB bundles were verified to contain Table 3.2.2.2 with wall values
and climate-zone headers. Bundles built with text-only extraction still require
table-aware re-ingestion.

Run retrieval regression tests from `surrogate-app/Code-Compliance`:

```bash
python -m unittest discover -s tests -v
```

## API endpoints

| Method | Path | Description |
|---|---|---|
| `GET`  | `/health` | Unauthenticated readiness check (used by ALB) |
| `GET`  | `/code-assistant/knowledge-bases` | Registry + load status + current model ID |
| `POST` | `/code-assistant/chat` | Non-streaming answer (JSON) |
| `POST` | `/code-assistant/chat/stream` | Server-Sent Events streaming answer |
| `GET`  | `/docs` | Swagger UI |

Request body for `/chat` and `/chat/stream`:
```json
{
  "message": "What is the max U-value for windows in Climate Zone 7?",
  "selected_codes": ["necb_2020", "necb_2025"],
  "history": [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}],
  "top_k": 6
}
```
