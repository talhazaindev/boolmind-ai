# Engineering Audit Report — boolmind-ai


---

## summary

The `dev` branch represents a **significant product evolution** beyond the original chat MVP. It delivers a **Boolmind Advisor** with product-aware conversation, 7-phase discovery flow, diagnosis engines, RAG over a structured `knowledge-base/`, tool integrations (CRM, calendar, email, tours, architecture/FIDP generation), Redis-backed sessions, Docker Compose for local stack, and a meaningful unit-test suite for orchestrator heuristics.

However, against the engineering standards listed in the audit brief, the codebase is **not production-ready**. The main gaps are:

1. **Dual parallel stacks** — legacy chat/voice (`app/services/`, `/chat`, `/voice`) coexists with the advisor stack (`app/advisor/`, `/api`), with different session stores, knowledge sources, and prompts.
2. **Security is opt-in** — CORS is fully open, HMAC is skipped when `CHAT_API_SECRET` is unset, admin and ops endpoints are unauthenticated, rate limits are in-process only.
3. **Architecture debt** — no enforced domain/application/infra boundaries; god files in orchestrator; inverted dependencies (`services` → `advisor`); ceremonial MCP layer with empty servers.
4. **Stub infrastructure** — failed-operation retry, partial dead code, and misleading abstractions that look complete but are not.
5. **Test gaps** — strong on pure orchestrator logic; weak on HTTP APIs, integrations, RAG pipeline, and security paths.

**Overall grade against stated standards: ~55/100** — strong prototype, requires structured remediation before production deployment.


## 1. Application inventory

### 1.1 Repository layout

```
boolmind-ai/
├── main.py                    # FastAPI bootstrap, routers, static UI, health
├── app/
│   ├── advisor/               # Primary product stack (NEW)
│   │   ├── orchestrator/      # Chat loop, diagnosis, prompts (~5,300 LOC)
│   │   ├── tools/             # Tool handlers (CRM, calendar, RAG, FIDP, …)
│   │   ├── rag/               # Embed, retrieve, Pinecone
│   │   ├── integrations/      # Groq/Ollama, Redis, Supabase, image gen
│   │   ├── mcp/               # MCP host, router, empty server shells
│   │   ├── analytics/         # PostHog events
│   │   ├── proactive/         # Proactive rules
│   │   ├── config/            # Product definitions
│   │   └── security.py        # HMAC, rate limit, sanitize
│   ├── api/                   # HTTP + WebSocket routes
│   ├── core/                  # Settings, dependencies, ML env
│   └── services/              # Legacy chat/voice stack
├── frontend/                  # index.html (legacy), advisor.html, admin.html
├── knowledge/                 # Legacy markdown KB (old chat)
├── knowledge-base/            # Advisor RAG source + product tours
├── widget/locales/            # i18n JSON only — no widget runtime
├── tests/                     # unit, integration, evals, e2e (skipped)
├── scripts/                   # ingest, evals, manual tests, smoke
├── docker-compose.yml         # Local stack (Redis, Pinecone local, Ollama, …)
└── docs/                      # Manual test plans and stale result reports
```

### 1.2 Feature delivery (what `dev` actually ships)

| Feature area | Status | Primary paths |
|--------------|--------|---------------|
| Streaming text chat (advisor) | **Implemented** | `app/api/advisor.py`, `app/advisor/orchestrator/loop.py` |
| 7-phase discovery flow | **Implemented** | `reasoning_engine.py`, `conversation_mode.py`, `loop.py` |
| Product-aware routing | **Implemented** | `intent_classifier.py`, `product_context.py`, `config/products.py` |
| Diagnosis engines | **Implemented** | `strategy_diagnosis.py`, `operations_diagnosis.py`, `workforce_diagnosis.py`, `profitability_diagnosis.py` |
| RAG retrieval | **Implemented** | `app/advisor/rag/` + `knowledge-base/` |
| Tool calling | **Implemented** | `mcp_tool_router.py`, `app/advisor/tools/*` |
| CRM / calendar / email tools | **Implemented** (env-dependent) | HubSpot, Cal.com, Resend integrations |
| FIDP / architecture image gen | **Implemented** (GPU/local/Replicate) | `generate_fidp.py`, `image_gen.py` |
| Redis sessions | **Implemented** | `integrations/redis_store.py` |
| Legacy chat + voice | **Still present** | `app/services/`, `/chat`, `/voice` |
| Admin dashboard | **Implemented** (unauthenticated) | `frontend/admin.html`, `/api/admin/stats` |
| Docker local stack | **Implemented** | `docker-compose.yml`, `Dockerfile`, `Dockerfile.gpu` |
| CI unit tests | **Partial** | `.github/workflows/advisor-evals.yml` |

---

## 2. Architecture audit

### 2.1 Expected vs actual layering

The audit brief requires clear boundaries between **domain**, **application**, **infrastructure**, and **interfaces**. The codebase uses **feature folders** only. There is no `domain/` package, no port/adapter pattern, and no dependency rule enforcement.

| Intended layer | Where it lives today | Quality |
|----------------|---------------------|---------|
| Domain types & rules | Scattered: `types.py`, `orchestrator/*`, `config/products.py` | **Weak** — domain mixed with prompts and infra |
| Application / use cases | `orchestrator/loop.py`, `chat_service.py` | **Poor** — god orchestrator |
| Infrastructure | `integrations/`, `rag/`, `services/stt|tts/` | **Acceptable grouping** |
| Interfaces (HTTP/WS) | `app/api/*`, `main.py` | **Mixed** — some thin, some fat |

### 2.2 CRITICAL: Dual parallel chat stacks

Two independent chat systems are mounted simultaneously:

| Aspect | Legacy stack | Advisor stack |
|--------|--------------|---------------|
| HTTP routes | `/chat/stream`, `/sessions/*` | `/api/chat`, `/api/chat-init`, `/api/chat-clear` |
| Service | `app/services/chat_service.py` | `app/advisor/orchestrator/loop.py` |
| Session store | In-memory `SessionManager` | Redis `redis_store.py` |
| Knowledge | `knowledge/*.md` file injection | `knowledge-base/` + Pinecone RAG |
| System prompt | Hardcoded `DEFAULT_SYSTEM_PROMPT` in `chat_service.py` | `buildSystemPrompt()` in `system_prompt.py` |
| Frontend | `frontend/index.html` | `frontend/advisor.html` |
| Voice pipeline | **Uses legacy `ChatService`** | Not integrated |

**Impact:** Voice users (`app/services/voice_pipeline.py`) receive the **old** prompt and knowledge, not the advisor experience. Maintenance cost doubles. Session semantics differ between UIs.

**Finding ARCH-001 (Critical):** Unify or explicitly deprecate legacy stack; route voice through advisor loop.

### 2.3 Inverted dependencies

**Finding ARCH-002 (High):** `app/services/groq_client.py` imports from `app.advisor.integrations.groq_llm`. The legacy layer depends on the new advisor infrastructure. Clean architecture requires the opposite: advisor/legacy should depend on abstractions, infra should implement them.

**Finding ARCH-003 (High):** Tool handlers import `ProductContext` from `orchestrator.product_context` — tools depend on orchestrator internals instead of a shared domain module.

### 2.4 God files and complexity hotspots

| File | Lines | Concern |
|------|-------|---------|
| `orchestrator/reasoning_engine.py` | 601 | Hypotheses, heuristics, regex signals, prompt blocks in one module |
| `orchestrator/loop.py` | 523 | Full chat pipeline: evaluate → diagnose → prompt → tool rounds → synthesis → rewrite |
| `orchestrator/conversation_evaluator.py` | 399 | Per-turn LLM judge |
| `orchestrator/strategy_diagnosis.py` | 331 | Growth diagnosis |
| `orchestrator/operations_diagnosis.py` | 287 | Throughput diagnosis |
| `api/voice_ws.py` | 260 | WebSocket protocol + providers + pipeline in one handler |
| `core/config.py` | 254 | Single settings object for all tiers and integrations |

**Finding ARCH-004 (Critical):** `loop.py` is a god orchestrator — 20+ internal imports, multiple LLM calls per user turn (evaluator + main stream + up to 5 tool rounds + synthesis + optional rewrite). Not modular or easily testable in isolation.

**Finding ARCH-005 (High):** Diagnosis signal updates are duplicated across `loop.py`, `recommendation.py`, and four `*_diagnosis.py` modules.

### 2.5 MCP layer — ceremonial architecture

Four MCP server files exist under `app/advisor/mcp/servers/`:

- `knowledge_server.py`
- `crm_server.py`
- `calendar_server.py`
- `experience_server.py`

Each file only instantiates an empty `FastMCP` instance with **no tools registered**. Example (`crm_server.py`):

```python
crm_mcp = FastMCP("boolmind-crm")
# Tool registration for external MCP hosts; runtime chat uses McpToolRouter → handlers.
```

Actual tool execution flows: `AdvisorChatLoop` → `McpToolRouter` → Python handlers in `app/advisor/tools/`.

`mount.py` exposes SSE endpoints at `/mcp/*` but swallows mount failures silently (`except Exception: pass`).

**Finding ARCH-006 (High):** MCP folder structure implies external protocol boundaries that do not exist at runtime. Either register tools on FastMCP servers and use them, or remove empty servers/mounts and rename router to `ToolRouter` to avoid false layering.

### 2.6 Dead and duplicate code paths

| Item | Location | Issue |
|------|----------|-------|
| `handlers.execute_tool` | `app/advisor/tools/handlers.py` | Handles only 4 tools; **never called**; superseded by `McpToolRouter` |
| `latency.py` | `app/advisor/latency.py` | `LatencyTracker` defined; **never imported** elsewhere |
| Tool dispatch | `handlers.py` vs `mcp_tool_router.py` | Parallel if/elif chains for same tool names |
| `constants.py` vs `config/products.py` | Both define product metadata | Partial duplication |

**Finding ARCH-007 (Medium):** Remove dead code or wire it; duplication increases drift risk.

### 2.7 Global singletons (hidden magic)

| Singleton | Location | Risk |
|-----------|----------|------|
| MCP router | `mcp_tool_router.py` | Hard to test; single global instance |
| LLM client | `integrations/groq_llm.py` | Shared client state |
| Redis store | `integrations/redis_store.py` | `get_redis_store()` global |
| BGE embed model | `rag/embed.py` | Lazy load into module global — heavy cold start |
| Rate limit buckets | `security.py` `_RATE_BUCKETS` | Process-local |

**Finding ARCH-008 (Medium):** Prefer explicit dependency injection via FastAPI `Depends()` for testability and multi-instance correctness.

### 2.8 `main.py` composition root concerns

**Finding ARCH-009 (Medium):** `main.py` mixes concerns:

- CORS middleware (security)
- Router registration (composition)
- `/health` exposing internal config (key pool size, tier readiness)
- Unauthenticated `/admin` route
- Static file serving for frontend and FIDP output
- Import-time `configure_ml_environment()` side effect
- Optional Sentry init

No API versioning (`/api/v1`). Legacy and advisor routes coexist without deprecation headers.

---

## 3. Security audit

### 3.1 Summary

| Area | Severity | Status |
|------|----------|--------|
| Secrets in repository | Low | `.env` gitignored; placeholders in `.env.example` only |
| Authentication | **Critical gap** | Most routes unauthenticated |
| CORS | **High** | Wildcard origin + credentials |
| Input sanitization | Medium | `sanitize_message` on advisor; gaps elsewhere |
| Injection (SQL/command) | Low | No raw SQL; Supabase table names fixed at call sites |
| SSRF | Low | Outbound URLs are fixed vendor endpoints |
| Rate limiting | Medium | In-process, bypassable, not on all endpoints |
| PII in logs | Medium | Email logged in CRM tool |

### 3.2 Critical and high security findings

**SEC-001 (High) — Open CORS with credentials**

`main.py` lines 43–48:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    ...
)
```

Wildcard origin with credentials is unsafe and often invalid in browsers. Use an explicit allowlist per environment.

**SEC-002 (High) — Unauthenticated sensitive endpoints**

No auth middleware (`Depends`, API key, or Bearer) on:

| Endpoint | Risk |
|----------|------|
| `GET /admin` | Admin UI exposed |
| `GET /api/admin/stats` | Integration/config visibility |
| `POST /api/retry-failed-ops` | Callable by anyone (stub logic) |
| `GET /health` | Exposes key pool size, provider config |
| `GET /mcp/*` | MCP SSE mounts |
| `POST /chat/stream`, `/sessions/*` | Legacy chat abuse / cost |
| `/voice/*`, `/voice/ws` | TTS/STT cost abuse |

**SEC-003 (High) — HMAC optional**

`app/advisor/security.py`:

```python
def verify_chat_signature(request: Request, body: bytes) -> None:
    if not settings.chat_api_secret:
        return  # verification skipped entirely
```

Default dev configuration leaves `/api/chat` unsigned.

**SEC-004 (Medium) — Rate limiting weaknesses**

- `_RATE_BUCKETS` is in-process `defaultdict` — ineffective across workers/replicas; resets on restart.
- `client_ip()` trusts first `X-Forwarded-For` hop — spoofable without trusted reverse proxy configuration.
- Applied to `/api/chat` and `/api/chat-init` only; **`/api/chat-clear` has neither HMAC nor rate limit**.

**SEC-005 (Medium) — Information disclosure in errors**

`app/api/advisor.py` yields SSE error events with `str(e)[:200]` to clients. Contrast `loop.py` which returns generic messages for Groq failures. Inconsistent and may leak internals.

**SEC-006 (Medium) — Malformed JSON on `/api/chat`**

`json.loads(raw)` without try/except — malformed body likely returns HTTP 500 instead of structured SSE error (project spec says avoid 500 on chat path).

### 3.3 Security positives

- `sanitize_message()` strips HTML tags and caps length (2000 chars).
- HMAC implementation uses `hmac.compare_digest` and 60-second replay window when enabled.
- RAG namespaces centrally allowlisted in `app/advisor/rag/namespaces.py`.
- CRM duplicate-email guard per visitor in `crm_create_lead.py`.
- No bare `except:` clauses in codebase.
- `.env` is gitignored; no committed API keys found in source.

---

## 4. Code quality audit

### 4.1 Typing

**Finding CQ-001 (Medium):** Widespread `dict[str, Any]` and `Any` return types in:

- `app/advisor/integrations/groq_llm.py`
- `app/advisor/orchestrator/loop.py`
- `app/advisor/mcp/mcp_tool_router.py`
- All `app/advisor/tools/*.py` (`arguments: dict[str, Any]`)

Tool JSON schemas live in `orchestrator/tools.py` as static JSON — not enforced as Pydantic models at handler boundaries.

**Finding CQ-002 (Low):** ~8 uses of `# type: ignore` in orchestrator/session code for enum workarounds.

### 4.2 Error handling

**Finding CQ-003 (Medium) — Swallowed exceptions**

| Location | Behavior |
|----------|----------|
| `orchestrator/loop.py:516-517` | `except Exception: pass` — rewrite synthesis silently dropped |
| `api/voice_ws.py:260,279` | `except Exception: pass` on cleanup |
| `advisor/mcp/mount.py:20-22` | MCP mount failure swallowed |
| `integrations/redis_store.py:108-110` | `ping()` exception handling may mask failures |

**Finding CQ-004 (Medium) — Inconsistent error contracts**

| Endpoint family | Error shape |
|-----------------|-------------|
| Advisor chat | SSE `{"type":"error","code":...}` |
| Legacy chat | SSE `event: error` |
| Voice HTTP | JSON 502/503 with `str(e)` |
| Sessions | `HTTPException` 404/409 |

Clients must handle multiple patterns.

### 4.3 Timeouts and cancellation

**Implemented (good):**

- Tool execution: `asyncio.wait_for` via `TOOL_TIMEOUT_MS` in `mcp_tool_router.py` and `handlers.py`
- httpx outbound calls: 8–10s timeouts (CRM, Cal.com, Resend, Supabase)
- Conversation evaluator: `EVAL_TIMEOUT_MS`
- Voice pipeline: `wait_for(audio_task, 60.0)` with cancellation

**Finding CQ-005 (Medium) — Unbounded LLM streams**

`integrations/groq_llm.py` and `services/groq_client.py` have no overall `wait_for` on Groq/Ollama `create` or stream iteration. A hung upstream can hold connections indefinitely.

### 4.4 Logging

**Finding CQ-006 (Medium):** Stdlib `logging.basicConfig` with text format — not structured JSON. No correlation IDs across a chat turn.

**Finding CQ-007 (Medium) — Sensitive data in logs**

| Location | Data logged |
|----------|-------------|
| `tools/crm_create_lead.py` | Visitor email |
| `integrations/groq_llm.py` | Last 6 chars of API key |
| `api/voice_ws.py` | Transcript preview (80 chars) |
| `services/voice_pipeline.py` | Sentence preview in Rich panels |

PostHog analytics path correctly uses session IDs only (no PII per docstring).

### 4.5 Stub / placeholder behavior in production paths

**Finding CQ-008 (High) — Failed operations queue is fake retry**

`integrations/failed_operations.py` uses process-local `_memory_queue` (lost on restart).

`POST /api/retry-failed-ops` in `advisor.py` increments `retries` counter and optionally clears queue — **does not replay** CRM/calendar/email operations.

**Finding CQ-009 (Low) — Intentional mocks when integrations unconfigured**

- Cal.com unconfigured → `mock-{email}` booking UID
- FIDP → placeholder SVG when image gen unavailable

Document clearly in ops runbooks; do not present as production behavior.

---

## 5. Testing audit

### 5.1 Test inventory

```
tests/
├── unit/           34 files — orchestrator-heavy (~120+ test functions)
├── integration/    2 files  — discovery flow metadata; SSE JSON shape
├── evals/          Ground-truth JSON + conversation scenario tests
└── e2e/            1 file   — permanently skipped
```

### 5.2 Well-covered areas

| Module / behavior | Test files |
|-------------------|------------|
| Conversation mode, intent, goal context | `test_conversation_mode.py`, `test_intent_classifier.py`, `test_goal_context.py` |
| Diagnosis (strategy, operations, workforce) | `test_strategy_diagnosis.py`, `test_operations_diagnosis.py`, `test_workforce_diagnosis.py` |
| Tool gating, response guards, system prompt | `test_tool_gating.py`, `test_response_guards.py`, `test_system_prompt.py` |
| Product context, namespaces | `test_product_context.py`, `test_namespaces.py` |
| LLM provider selection, Groq rotation | `test_llm_provider.py`, `test_groq_rotation.py` |
| MCP router (mocked, partial) | `test_mcp_router.py` |
| Security sanitize | `test_security.py` (sanitize only) |

### 5.3 Coverage gaps

| Severity | Gap | Paths |
|----------|-----|-------|
| **High** | No HTTP/API tests (`TestClient`) | `app/api/advisor.py`, `chat.py`, `sessions.py`, `voice*.py` |
| **High** | Tool handlers untested end-to-end | `crm_create_lead.py`, `calendar_*.py`, `send_meeting_invite.py`, `generate_*` |
| **High** | RAG pipeline untested | `rag/embed.py`, `retrieve.py`, `chunk.py`, `pinecone_index.py` |
| **High** | Security: no HMAC, rate limit, or replay tests | `security.py` |
| **High** | `reasoning_engine.py` (601 lines) — no direct tests | `orchestrator/reasoning_engine.py` |
| **Medium** | `ab_testing.py` wired in hot path, zero tests | `ab_testing.py`, `loop.py` |
| **Medium** | Integrations untested | `supabase_client.py`, `failed_operations.py`, `analytics/events.py` |
| **Medium** | Redis: factory tested only; no integration test | `redis_store.py` |
| **Low** | E2E skipped | `tests/e2e/test_advisor_smoke.py` |
| **Low** | `test_sse_format.py` mislabeled — JSON shape unit test, not integration | `tests/integration/` |

### 5.4 CI issues

**Finding TEST-001 (High):** `.github/workflows/advisor-evals.yml`:

- Uses **Python 3.12**; `pyproject.toml` pins `>=3.11,<3.12`
- Installs `requirements.txt` instead of `uv sync` / `uv.lock`
- `requirements.txt` missing `redis` (needed for `LocalRedisSessionStore` in some paths)
- RAG evals only on `workflow_dispatch` — not on every push
- No coverage gate (`pytest-cov` in dev extras only, never enforced)

---

## 6. Configuration and documentation audit

### 6.1 Configuration strengths

- Typed `Settings` via Pydantic Settings (`app/core/config.py`)
- `*_configured` and `advisor_tier_a_ready` helper properties
- Tiered `.env.example` sections (A/B/C/D capabilities)
- Separate `.env.docker.example` for Compose stack
- Docker Compose overrides for Redis/Pinecone local modes

### 6.2 Configuration findings

| ID | Severity | Finding |
|----|----------|---------|
| CFG-001 | High | `supabase_project_ref` hardcoded default `"jhoiqryisvxvtafvdwcf"` in `config.py` and `.env.example` |
| CFG-002 | High | `CHAT_API_SECRET` empty → all HMAC checks skipped |
| CFG-003 | Medium | `requirements.txt` vs `pyproject.toml` diverge (mcp version, posthog, torch pins, missing redis) |
| CFG-004 | Medium | `GROQ_KEY_POOL_SIZE` documented as 1..5 in `.env.example`; code supports 10 slots |
| CFG-005 | Medium | `get_groq_api_keys` docstring says "slot 32"; code scans 10 slots |
| CFG-006 | Low | `NEXT_PUBLIC_POSTHOG_KEY` in `.env.example` but not in `Settings` |
| CFG-007 | Low | `KNOWLEDGE_BASE_PATH` in `.env.example` for legacy; advisor uses `knowledge-base/` separately |

### 6.3 Documentation drift

| ID | Severity | Finding |
|----|----------|---------|
| DOC-001 | High | README says default TTS is `chatterbox`; `Settings.tts_provider` defaults to `deepgram` |
| DOC-002 | Medium | `.cursor/rules/boolmind-chatbot-spec.mdc` describes Next.js / Anthropic / Edge `/api/chat` — wrong stack for this Python repo |
| DOC-003 | Medium | `docs/advisor-test-results.md` shows stale ~14% pass rate — misleading if read as current |
| DOC-004 | Low | `pyproject.toml` description: `"Add your description here"` |
| DOC-005 | Low | `app/data/README.md` describes legacy `knowledge/` only, not advisor RAG |

---

## 7. Docker and deployment audit

### 7.1 Strengths

| Item | Assessment |
|------|------------|
| `docker-compose.yml` | Solid local stack: Redis healthcheck, Pinecone Local 384-dim, Ollama-on-host, `seed` profile for ingest |
| `docker-compose.cloud.yml` | Clean API-only cloud path |
| `Dockerfile` | Multi-stage `uv` build, non-root user, healthcheck, CPU torch via `docker-cpu` extra |
| `Dockerfile.gpu` | CUDA runtime, `fidp`+`gpu` extras, NVIDIA device reservation |
| Volumes | `huggingface-cache`, `fidp-output`, `redis-data` |

### 7.2 Deployment findings

| ID | Severity | Finding |
|----|----------|---------|
| DEP-001 | Medium | `chatterbox-tts` Compose profile references `chatterbox-tts-api:local` with no build context — image must be pre-built manually |
| DEP-002 | Medium | README GPU/FIDP paths are Windows-centric (`D:\...`); Docker uses `/data/...` |
| DEP-003 | Low | Long healthcheck `start_period` (180s/300s) — reasonable for BGE model load |
| DEP-004 | Low | No Kubernetes/Helm/Terraform — Compose-only deployment story |

---

## 8. Infrastructure stubs (production blockers)

| Component | Advertised behavior | Actual behavior | ID |
|-----------|--------------------|-----------------|-----|
| Failed ops retry | `POST /api/retry-failed-ops` | Increments counter; does not replay | CQ-008 |
| MCP servers | `/mcp/knowledge`, `/mcp/crm`, … | Empty FastMCP shells | ARCH-006 |
| Legacy sessions | `/sessions/{id}` | In-memory; lost on restart | ARCH-001 |
| Rate limits | `check_rate_limit()` | Per-process dict | SEC-004 |
| `handlers.execute_tool` | Tool dispatch | Dead code | ARCH-007 |

---

## 9. Positive findings (preserve these patterns)

1. **One file per tool** under `app/advisor/tools/` with centralized routing in `McpToolRouter`.
2. **RAG namespace allowlisting** in `namespaces.py` — good injection-prevention pattern.
3. **Tool timeouts** via `asyncio.wait_for` and configurable `TOOL_TIMEOUT_MS`.
4. **No bare `except:`** anywhere in application code.
5. **Pydantic models** for advisor request types, `SessionMetadata`, `PageContext`, `ToolResult`.
6. **HMAC design** (when enabled): timing-safe compare, replay window.
7. **Docker** multi-stage builds, non-root user, healthchecks.
8. **Unit tests for orchestrator heuristics** are substantive where they exist.
9. **Structured knowledge base** under `knowledge-base/products/`, capabilities, and tours JSON.
10. **Groq rate limit mapping** to `RATE_LIMIT` SSE events in main chat loop (avoids raw 500).

---

## 10. Prioritized remediation plan

### Phase 0 — Production blockers (do first)

| ID | Action | Owner hint |
|----|--------|------------|
| SEC-001 | Restrict CORS to explicit origins; remove `allow_credentials` or pair with named origins | Backend |
| SEC-002 | Add authentication to `/admin`, `/api/admin/*`, `/api/retry-failed-ops`, `/mcp/*` | Backend |
| SEC-003 | Require `CHAT_API_SECRET` in non-dev environments | Backend / DevOps |
| SEC-004 | Redis-backed rate limits; trusted proxy config for client IP; rate-limit `/api/chat-clear` | Backend |
| SEC-005 | Remove `str(e)` from client-facing errors | Backend |
| SEC-006 | Wrap `json.loads` on `/api/chat`; return SSE error events | Backend |
| CQ-005 | Add Groq/Ollama stream timeouts | Backend |
| ARCH-001 | Deprecate legacy `/chat` + route voice through advisor (or document explicit dual-product strategy) | Backend |

### Phase 1 — Architecture clarity

| ID | Action |
|----|--------|
| ARCH-002 | Introduce LLM port/interface; stop `services` importing `advisor` |
| ARCH-003 | Move `ProductContext`, `SessionMetadata` rules to `app/domain/` (or equivalent) |
| ARCH-004 | Split `loop.py` into pipeline stages with single responsibility |
| ARCH-006 | Delete empty MCP servers OR register tools and use them for real |
| ARCH-007 | Remove `handlers.execute_tool`, `latency.py` if unused |
| ARCH-008 | Wire DI via FastAPI `Depends()` for store, LLM, router |
| CQ-008 | Implement real failed-op retry queue (Redis/Supabase) or remove endpoint |

### Phase 2 — Quality bar

| ID | Action |
|----|--------|
| TEST-001 | Fix CI: Python 3.11, `uv sync`, add `redis` dep |
| — | Add API + security integration tests |
| — | Add direct tests for `reasoning_engine.py` or decompose it |
| CQ-001 | Pydantic models for tool arguments |
| CQ-006 | Structured logging (JSON); correlation ID per chat turn |
| CQ-007 | Redact PII from logs in production |
| DOC-001 | Align README and `.env.example` with `Settings` defaults |
| CFG-001 | Remove hardcoded Supabase project ref from defaults |

### Phase 3 — Production hardening

| ID | Action |
|----|--------|
| — | Enforce coverage gate in CI |
| — | Run RAG evals on push (or nightly) |
| — | Split `Settings` into `AdvisorSettings`, `VoiceSettings`, `IntegrationSettings` |
| DEP-001 | Document or automate Chatterbox image build in Compose |
| — | API versioning (`/api/v1`) |

---

## 11. Finding index (quick reference)

| ID | Severity | Category | Summary |
|----|----------|----------|---------|
| ARCH-001 | Critical | Architecture | Dual legacy + advisor chat stacks |
| ARCH-002 | High | Architecture | Inverted `services` → `advisor` dependency |
| ARCH-003 | High | Architecture | Tools import orchestrator internals |
| ARCH-004 | Critical | Architecture | God orchestrator in `loop.py` |
| ARCH-005 | High | Architecture | Duplicated diagnosis signal logic |
| ARCH-006 | High | Architecture | Empty MCP servers; ceremonial layer |
| ARCH-007 | Medium | Architecture | Dead code: `execute_tool`, `latency.py` |
| ARCH-008 | Medium | Architecture | Global singletons |
| ARCH-009 | Medium | Architecture | `main.py` mixed concerns |
| SEC-001 | High | Security | CORS wildcard + credentials |
| SEC-002 | High | Security | Unauthenticated admin/ops/voice/MCP |
| SEC-003 | High | Security | Optional HMAC |
| SEC-004 | Medium | Security | In-memory rate limits |
| SEC-005 | Medium | Security | Exception strings to clients |
| SEC-006 | Medium | Security | Unhandled JSON parse on chat |
| CQ-001 | Medium | Code quality | Heavy `Any` usage |
| CQ-003 | Medium | Code quality | Swallowed exceptions |
| CQ-004 | Medium | Code quality | Inconsistent error contracts |
| CQ-005 | Medium | Code quality | Unbounded LLM streams |
| CQ-006 | Medium | Code quality | Unstructured logging |
| CQ-007 | Medium | Code quality | PII in logs |
| CQ-008 | High | Code quality | Stub failed-op retry |
| TEST-001 | High | Testing | CI Python/dep drift |
| CFG-001 | High | Config | Hardcoded Supabase ref |
| CFG-002 | High | Config | HMAC disabled by default |
| DOC-001 | High | Docs | README TTS default wrong |
| DEP-001 | Medium | Deploy | Chatterbox image not in Compose build |

---

## 12. Appendix — orchestrator package file map

The `app/advisor/orchestrator/` package (~5,300 LOC across 27 files) is the core complexity center:

| File | Responsibility |
|------|----------------|
| `loop.py` | Main chat stream, tool rounds, persistence |
| `reasoning_engine.py` | Hypotheses, confidence, phases, prompt blocks |
| `conversation_evaluator.py` | Per-turn LLM quality judge |
| `system_prompt.py` | Static sections A–L + dynamic builder |
| `intent_classifier.py` | User intent detection |
| `conversation_mode.py` | Mode state machine |
| `goal_context.py` | Goal tracking across turns |
| `session_metadata.py` | Session enrichment |
| `product_context.py` | Product detection and context |
| `page_context.py` | Page/URL context from client |
| `diagnosis_router.py` | Routes to diagnosis engines |
| `strategy_diagnosis.py` | Growth/strategy signals |
| `operations_diagnosis.py` | Operations/throughput signals |
| `workforce_diagnosis.py` | Workforce signals |
| `profitability_diagnosis.py` | Profitability signals |
| `diagnostic_trees.py` | Tree structures for diagnosis |
| `diagnostic_validation.py` | Validation of diagnosis output |
| `recommendation.py` | Product recommendations |
| `response_guards.py` | Output guardrails |
| `tool_gating.py` | Which tools allowed when |
| `tool_args.py` | Tool argument helpers |
| `tools.py` | Tool JSON schema definitions |
| `industry_strategy.py` | Industry-specific strategy |
| `problem_dimension.py` | Problem dimension tracking |
| `custom_complexity.py` | Custom build complexity |
| `tech_depth.py` | Technical depth adjustment |

**Recommendation:** Treat this package as the primary refactoring target. Extract domain rules and ports before adding more product features.

---


