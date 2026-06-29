# Boolmind Advisor — Automated Test Run Results

**Run time:** 2026-06-03 11:27:03
**Base URL:** http://127.0.0.1:8000
**Delay between messages:** 12s (Groq rate-limit mitigation)

## Executive summary

| Metric | Count |
|--------|-------|
| Total cases | 7 |
| PASS | 1 |
| PARTIAL | 0 |
| FAIL / ERROR | 6 |
| **Pass rate (strict)** | 14% |
| **Pass rate (incl. partial)** | 14% |

### Production readiness (honest assessment)

| Integration | Configured |
|-------------|------------|
| Groq | False |
| Pinecone | True |
| Redis | True |
| HubSpot | True |
| Cal.com | False |
| Resend | True |
| Supabase | False |
| HMAC (`CHAT_API_SECRET`) | False |

## Detailed results

| ID | Status | Tools seen | Notes |
|----|--------|------------|-------|
| INFRA-health | **FAIL** | — | tier_a=False |
| INFRA-admin | **PASS** | — | admin stats ok |
| INFRA-init-general | **ERROR** | — | Server error '503 Service Unavailable' for url 'http://127.0.0.1:8000/api/chat-init'
For more information check: https:/ |
| INFRA-init-ecg | **ERROR** | — | Server error '503 Service Unavailable' for url 'http://127.0.0.1:8000/api/chat-init'
For more information check: https:/ |
| INFRA-init-compare | **ERROR** | — | Server error '503 Service Unavailable' for url 'http://127.0.0.1:8000/api/chat-init'
For more information check: https:/ |
| H3-returning | **ERROR** | — | Server error '503 Service Unavailable' for url 'http://127.0.0.1:8000/api/chat-init'
For more information check: https:/ |
| H2-clear | **ERROR** | — | Server error '503 Service Unavailable' for url 'http://127.0.0.1:8000/api/chat-init'
For more information check: https:/ |

## Response excerpts (failures / partials)

### INFRA-health (FAIL)
Tools: `none`
```
{"status": "ok", "groq_configured": false, "groq_key_pool_size": 0, "advisor_tier_a_ready": false}
```

### INFRA-init-general (ERROR)
Tools: `none`
```

```

### INFRA-init-ecg (ERROR)
Tools: `none`
```

```

### INFRA-init-compare (ERROR)
Tools: `none`
```

```

### H3-returning (ERROR)
Tools: `none`
```

```

### H2-clear (ERROR)
Tools: `none`
```

```
