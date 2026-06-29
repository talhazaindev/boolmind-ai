# Boolmind Advisor — Manual Test Plan

Use this document for **manual end-to-end testing** on `http://127.0.0.1:8000/advisor` (or your deployed URL).

**Before you start**

1. Server running with Tier A keys: `GROQ_*`, `PINECONE_*`, `UPSTASH_*`, `EMBEDDING_PROVIDER=local`
2. Ingest done: `python scripts/run_ingest.py --namespace all`
3. Open browser DevTools → **Network** → filter `chat` / `chat-init` to see SSE events
4. For each test, note: **SSE `tool_start` / `tool_result`**, UI behavior, and assistant text

**SSE events to watch**

| Event | Meaning |
|--------|---------|
| `tool_start` | Tool name + input (confirms which tool fired) |
| `tool_result` | Tool payload (tour JSON, comparison table data, etc.) |
| `delta` | Streaming assistant text |
| `done` | Turn complete; may include `activeProduct`, `productsDiscussed` |

**Pass criteria (general)**

- Factual answers grounded in KB (not invented step counts)
- Correct tool used for the intent (see tables below)
- No HTTP 500 — errors appear as SSE `error` or system bubble
- Hard rules: no pricing quotes, no phone/company-size asks, no “identical features” claim

---

## 1. Tool coverage matrix

Run at least one query per tool per persona where noted.

| Tool | How to trigger | UI signal |
|------|----------------|-----------|
| `rag_query` | Any factual product question | Typing: “Searching knowledge base…” |
| `product_compare` | Compare 2–3 products | Comparison table in chat |
| `product_tour` | “Give me a tour…” | Tour card with steps + Back/Next |
| `crm_create_lead` | Provide name + email after interest | Silent; check HubSpot or logs |
| `calendar_get_slots` | “What times are available?” | Assistant lists slots (or mock slots) |
| `calendar_book_slot` | Pick slot + name + email | Booking confirmation text |
| `send_meeting_invite` | After book (often chained) | Mentions email sent / queued |
| `generate_architecture_proposal` | Technical solution / architecture ask | Structured proposal in reply |
| `generate_fidp` | “Show me a visual preview” | Image URL or placeholder card |

**Non-tool flows**

| Flow | How to test |
|------|-------------|
| `chat-init` | Reload `/advisor` — opening message + sessionId |
| Page context | `/advisor?product=ecg` — ECG-focused opening |
| Product selector | Header dropdown → badge updates |
| Clear chat | **Clear chat** — new session, empty history |
| Returning visitor | Same browser after prior chat — welcome-back tone |
| Proactive | Stay on page / scroll (toasts may appear) |
| Pricing refusal | “How much does Retify cost?” |
| Rate limit / HMAC | Only if `CHAT_API_SECRET` set in `.env` |

---

## 2. Personas

| Persona | Profile | Language style | Depth expected |
|---------|---------|----------------|----------------|
| **Naive** | Business user, no data engineering background | Simple, outcome-focused | Short answers, no jargon |
| **Semi-technical** | Analyst / IT manager, knows systems but not pipelines | Mix of business + some technical terms | Workflow steps, formats, integrations |
| **Technical** | Engineer / architect | APIs, schemas, EMR, FHIR, pipelines | Deep workflow, architecture mode |

Use **separate chat threads** per persona (new session or **Clear chat** between major threads).

---

## 2.5 Discovery funnel (Phase 7)

**Setup:** New session on `http://127.0.0.1:8000/advisor`. Watch SSE `done` for `stage`, `missingFields`, and `readiness`.

| # | You send (query) | Expected tool(s) | Expected behavior |
|---|------------------|------------------|-------------------|
| DF1 | What is Retify? | `rag_query` | Answers from KB. Ends with **one** discovery question. **No** tour card on turn 1. `done.stage` likely `EXPLORE` or `INTEREST`. |
| DF2 | Design our full system architecture now | None (gated) | Brief orienting answer only. **No** `generate_architecture_proposal`. Follow-up asks business context (industry, pain, goals). |
| DF3 | (After DF1–DF2) I run 40 retail stores, POS data is fragmented, goal is unified weekly reporting, sources are Shopify + NetSuite. | `rag_query` optional | `done.readiness.product_tour` may become true. Stage advances toward `QUALIFY`. Assistant may offer tour when ready. |
| DF4 | Reload same browser after DF3 (returning visitor) | — | Opening or reply references prior context. Does **not** re-ask industry/pain/goals already captured. |

**Discovery funnel pass:** Answer + one question every turn; gated deliverables blocked until `readiness` flags true; `stage` updates in `done` events.

---

## 2.6 Forecasting Engine (catalog product)

**Setup:** `http://127.0.0.1:8000/advisor?product=forecasting` or header selector → Forecasting Engine.

| # | You send (query) | Expected tool(s) | Expected behavior |
|---|------------------|------------------|-------------------|
| F1 | We need to predict weekly sales by store and SKU with weather impact | `rag_query` (`forecasting`) | Describes 8-step Forecasting Engine workflow; weather/promo/inventory capabilities. Ends with discovery question. |
| F2 | How is this different from Retify? | `rag_query` or `product_compare` | Retify unifies data; Forecasting predicts demand. Distinct products. |
| F3 | Give me a tour | `product_tour` (`forecasting`) if readiness | Forecasting tour card when gated; else defer + question. |

---

## 2.7 Custom solutions (fleet / transportation)

**Setup:** New session, no product query param.

| # | You send (query) | Expected tool(s) | Expected behavior |
|---|------------------|------------------|-------------------|
| C1 | I run a transportation company and need fleet management with driver workload ML | `rag_query` (`capabilities`) | Routes to **custom solutions** — Boolmind builds bespoke web/mobile/AI. Does **not** push Retify/ECG/Legal as primary fit. |
| C2 | I need to see a demo | None / architecture if ready | **No** catalog `product_tour`. Acknowledge + discovery question OR architecture proposal when readiness allows. |
| C3 | Everything is managed manually today | `rag_query` | Continues discovery; may mention custom automation. |
| M1 | Retail POS data is fragmented across stores | `rag_query` (`retify`) | Recommends **Retify**, not custom solutions. |

**Custom solutions pass:** Fleet/transport → capabilities KB; no forced catalog product; no catalog tour for custom fit.

---

## 3. Thread A — Naive customer (general discovery)

**Setup:** Open `http://127.0.0.1:8000/advisor` (no `?product=`). New session.

| # | You send (query) | Expected tool(s) | Expected assistant behavior |
|---|------------------|------------------|----------------------------|
| A1 | Hi, what does Boolmind actually do? | `rag_query` (namespace `general` or `all`) | Mentions catalog products (Retify, ECG, Legal, Forecasting) and custom solutions. No pricing. Friendly, short. |
| A2 | I run a chain of stores and our sales data is a mess. Which product fits? | `rag_query` (`retify`) | Recommends **Retify** — retail unification. May ask what sources (POS, ERP) without asking email yet. |
| A3 | Can you walk me through it? | `product_tour` (`retify`) if readiness allows | **Tour card** when discovery context is sufficient; otherwise brief explanation + discovery question. |
| A4 | How is that different from your medical product? | `product_compare` or `rag_query` | Compares Retify vs ECG; states **10 vs 7 steps**, different verticals. Does **not** say they are the same. |
| A5 | What does it cost? | None required | **Refuses pricing**; offers to connect with team / discovery call. No dollar amounts. |
| A6 | OK I’m interested — my name is Sam Lee and email sam.lee@example.com, we need help unifying store data. | `crm_create_lead` | Acknowledges next steps; does **not** ask for phone or company size. Lead in HubSpot if configured. |
| A7 | Can I book a call? | `calendar_get_slots` → possibly `calendar_book_slot` | Shows available slots (real Cal.com or mock). Guides to pick time. |

**Thread A pass:** Tours work, compare/RAG accurate, pricing blocked, lead capture without phone.

---

## 4. Thread B — Semi-technical customer (ECG focus)

**Setup:** Open `http://127.0.0.1:8000/advisor?product=ecg`. Confirm opening mentions ECG / scanned PDFs.

| # | You send (query) | Expected tool(s) | Expected behavior |
|---|------------------|------------------|-------------------|
| B1 | (Observe only) | — | Opening: ECG Document Intelligence; scanned ECGs vs waveforms question. |
| B2 | We get Holter PDFs and some WFDB exports. What can you ingest? | `rag_query` (`ecg`) | Lists PDF, images, CSV, **WFDB**, **EDF**. Mentions 7-step workflow at high level. |
| B3 | What happens in the OCR step? | `rag_query` (`ecg`) | Describes multilingual OCR / clinical text extraction (from KB). |
| B4 | Show me a tour of ECG | `product_tour` (`ecg`) | **ECG tour card** (5 steps). `tool_result` has `productId: ecg`. |
| B5 | Compare ECG and Legal Data Fusion for our hospital legal team — wrong fit on purpose | `product_compare` | Table with 2–3 rows; clarifies clinical vs legal use cases. |
| B6 | We’re also looking at retail analytics for the gift shop — is ECG enough? | `rag_query` + guidance | Suggests **Retify** for retail; keeps ECG for clinical docs. |
| B7 | I want a demo Tuesday next week — name Alex Kim, alex.kim@hospital.org | `calendar_get_slots` → `calendar_book_slot` → maybe `send_meeting_invite` | Booking flow; product context in notes if booked. |

**Thread B pass:** ECG namespace answers, ECG tour, compare table, cross-sell to Retify when appropriate.

---

## 5. Thread C — Semi-technical customer (Legal focus)

**Setup:** `http://127.0.0.1:8000/advisor?product=legal`

| # | You send (query) | Expected tool(s) | Expected behavior |
|---|------------------|------------------|-------------------|
| C1 | What is Legal Data Fusion in plain English? | `rag_query` (`legal`) | 6-step pipeline, golden records, heterogeneous legal datasets. |
| C2 | We have contracts CSV and matter exports in JSON. Supported? | `rag_query` (`legal`) | **CSV, JSON, XLSX** at ingest. |
| C3 | Give me a walkthrough | `product_tour` (`legal`) | Legal tour card (5 steps). |
| C4 | Compare all three Boolmind products for a general counsel office | `product_compare` | 3-row comparison table; legal vs retail vs clinical distinguished. |
| C5 | My email is jordan@lawfirm.example — name Jordan Reese, we need dataset consolidation. | `crm_create_lead` | Lead captured; `products_discussed` includes `legal`. |

**Thread C pass:** Legal KB + tour + three-way compare + CRM.

---

## 6. Thread D — Technical customer (Retify + architecture)

**Setup:** New session. Header product selector → **Retify** (or `?product=retify`).

| # | You send (query) | Expected tool(s) | Expected behavior |
|---|------------------|------------------|-------------------|
| D1 | Map Retify’s pipeline to our stack: POS from Shopify, ERP logs, warehouse in Snowflake. | `rag_query` (`retify`) | References **10-step** workflow: ingest, schema detection, entity matching, etc. |
| D2 | Which step handles entity resolution across SKU and store IDs? | `rag_query` (`retify`) | Points to entity matching / golden records (Step 4 area). |
| D3 | Design a technical architecture for ingesting multi-format retail feeds into Snowflake with schema drift handling. | `generate_architecture_proposal` | Structured reply: requirements, Mermaid, components (Boolmind vs External), phases, risks. SSE `tool_start` for `generate_architecture_proposal`. |
| D4 | Show me a UI mockup / visual preview for this pipeline | `generate_fidp` | Image URL or placeholder; brand colors noted in metadata. |
| D5 | Compare Retify workflow step count vs ECG and Legal explicitly | `product_compare` (`workflow` focus) | **10 / 7 / 6** steps from KB excerpts, not hardcoded fluff. |
| D6 | Give me the Retify tour from step 3 | `product_tour` (`retify`, `start_step: 3`) | Tour starts at later step if model passes `start_step`. |

**Thread D pass:** Deep RAG, architecture proposal, FIDP, explicit step-count compare.

---

## 7. Thread E — Technical customer (ECG clinical)

**Setup:** `?product=ecg`, new session after Clear chat.

| # | You send (query) | Expected tool(s) | Expected behavior |
|---|------------------|------------------|-------------------|
| E1 | How do you normalize QT and QRS into an EMR-friendly schema? | `rag_query` (`ecg`) | Normalization / validation / standardized schema (from KB). |
| E2 | HIPAA deployment model for on-prem OCR only? | `rag_query` (`ecg`, compliance) | Compliance-aware deployment; no PHI to external AI when restricted. |
| E3 | Architecture for hospital PACS → OCR → FHIR Observation resources | `generate_architecture_proposal` (`primary_product: ecg`) | ECG-centric components, EMR/FHIR in stack, data flow diagram. |
| E4 | 12-lead printout JPEG quality is poor — which preprocessing step helps? | `rag_query` (`ecg`) | Image preprocessing: skew, noise, grid lines. |

**Thread E pass:** Clinical depth + architecture mode on ECG.

---

## 8. Thread F — Multi-product & context switching

**Setup:** General `/advisor`, no product query param.

| # | You send (query) | Expected tool(s) | Expected behavior |
|---|------------------|------------------|-------------------|
| F1 | Compare Retify and ECG only — we’re not interested in legal | `product_compare` (`product_ids: [retify, ecg]`) | Table with **2 rows** only. |
| F2 | Actually we’re a law firm with billing spreadsheets | `rag_query` (`legal`) | Pivots to Legal Data Fusion; `done.activeProduct` may be `legal`. |
| F3 | Tour for that product | `product_tour` (`legal`) | Legal tour after context switch. |
| F4 | Use header dropdown → **ECG** then ask: “How many steps?” without typing product name | `rag_query` (auto `ecg`) | Answer **7 steps** using page/selector context. |

**Thread F pass:** Compare subset, context switch, selector affects namespace.

---

## 9. Thread G — Booking & invite chain (semi-technical)

**Setup:** Tier B Cal.com + Resend in `.env` for real slots; otherwise expect **mock** slots.

| # | You send (query) | Expected tool(s) | Expected behavior |
|---|------------------|------------------|-------------------|
| G1 | I’d like to schedule a discovery call next week | `calendar_get_slots` | Returns slot list (dates/times). Assistant asks timezone if needed. |
| G2 | Book the first slot — I’m Morgan Taylor, morgan.t@company.com, timezone UTC | `calendar_book_slot` | `status: booked` or `queued` in `tool_result`. Confirmation message. |
| G3 | (If book succeeded) Send me the invite email | `send_meeting_invite` | `status: sent` or queued; mentions Boolmind confirmation. |

**Thread G pass:** Full calendar chain visible in SSE order.

---

## 10. Thread H — Lead capture & returning visitor

**Setup:** Two sessions in same browser (keep `boolmind_vid` in localStorage).

| # | Step | Expected behavior |
|---|------|-------------------|
| H1 | Thread 1: Discuss Retify, then give name + email once | `crm_create_lead` once; second email in **same session** should not duplicate (status `duplicate` if same email). |
| H2 | **Clear chat** | Messages cleared; new `sessionId`; opening message for current page. |
| H3 | Reload page without clearing localStorage | `chat-init`: `isReturning: true`; welcome-back mentions last topic if metadata exists. |
| H4 | Ask factual question again | Still helpful; does not re-ask for name/email immediately (stage rules). |

---

## 11. Thread I — Refusals & guardrails (any persona)

| # | You send (query) | Expected tool(s) | Expected behavior |
|---|------------------|------------------|-------------------|
| I1 | What’s your price for 500 stores? | None | No price; offer human contact. |
| I2 | Call me at 555-123-4567 to discuss | None | Does **not** ask to store phone; may ask email only at CAPTURE stage. |
| I3 | How many employees does your company have? | None | Does not ask company size for lead capture. |
| I4 | Retify and ECG have the exact same features right? | `rag_query` / `product_compare` | **Corrects** user — distinct workflows, not interchangeable. |
| I5 | Tell me about Product X that Boolmind doesn’t sell | `rag_query` or none | Says unknown / sticks to three products; does not invent Product X. |

---

## 12. UI & API checks (quick checklist)

| Check | Steps | Expected |
|-------|--------|----------|
| Health | `GET /health` | `advisor_tier_a_ready: true` |
| Admin | `GET /admin` | JSON stats for integrations |
| Compare page | Visit with URL containing `compare` (if routed) or simulate via `page_context` | Compare-focused opening from `chat-init` |
| Proactive toast | Scroll page on product URL | Optional toast: tour suggestion |
| Clear during stream | Send message, click Clear while streaming | Clear disabled while streaming; works after done |
| SSE error handling | Stop Redis / bad key temporarily | SSE `error` event, not blank 500 page |

---

## 13. Suggested test order (one day)

1. **Smoke:** A1, B1, health check, one tour (A3)  
2. **All tools:** D3, D4, F1, G1–G3, C5, A6  
3. **Personas full threads:** A → B → D → E  
4. **Guardrails:** Thread I  
5. **Memory:** Thread H  

---

## 14. Recording results

Copy this table per session:

| Test ID | Pass / Fail | Tool seen in SSE? | Notes |
|---------|-------------|-------------------|-------|
| A1 | | | |
| … | | | |

**Common failures to watch for**

- Wrong step count (10/7/6) → ingest or `rag_query` namespace wrong  
- Tour missing → `knowledge-base/tours/{product}.json` or wrong `product_id`  
- Compare empty → Pinecone namespaces `ecg`/`legal` not ingested  
- CRM silent fail → `HUBSPOT_ACCESS_TOKEN` / custom properties  
- Calendar mock only → `CALCOM_*` not set (expected in dev)  
- No `tool_start` but answer looks factual → model skipped RAG (note for prompt tuning)

---

## 8. Consulting behavior (SMB / music academy persona)

Use a non-technical SMB persona (e.g. music academy, ~80 students, manual ops, limited budget).

| Test | User message | Pass criteria |
|------|--------------|---------------|
| CB1 | "What would you do in the next 3 months?" | Phased plan with Boolmind next step; not only a question |
| CB2 | "Why not Wix?" | Brief Wix trade-off; Boolmind differentiation as primary answer |
| CB3 | "Is $5000 worth it?" | ROI framework explained before asking for metrics |
| CB4 | "I'm not technical" (then any follow-up) | No RBAC/user-management jargon |
| CB5 | 3+ turns of discovery | Never more than 2 consecutive question-only turns |
| CB6 | Before value delivered | No name/email ask |
| CB7 | "Biggest reason NOT to hire Boolmind?" | Reframes to value/phased entry; does not say "don't hire us" as default |

Watch SSE `done` event for `conversationMode` (`discover`, `advise`, `recommend`, `deliver`).

---

*Document version: aligned with 9 advisor tools (`rag_query`, `product_compare`, `product_tour`, `crm_create_lead`, `calendar_get_slots`, `calendar_book_slot`, `send_meeting_invite`, `generate_architecture_proposal`, `generate_fidp`) and `/advisor` UI.*
