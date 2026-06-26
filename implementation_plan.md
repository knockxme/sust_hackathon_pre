# QueueStorm Investigator — Implementation Plan

## Overview

Build a production-ready AI/API service called **QueueStorm Investigator** — a support ticket analysis copilot for a digital finance platform (like bKash). It must expose two HTTP endpoints:
- `GET /health` → `{"status": "ok"}`
- `POST /analyze-ticket` → Structured JSON analysis of a customer complaint

The service uses **Groq's `qwen/qwen3-27b`** model with **Pydantic structured output** to analyze complaints in English, Bangla, or mixed Banglish and route them intelligently.

---

## Scoring Strategy (100 pts)

| Category | Weight | Our Strategy |
|---|---|---|
| Evidence Reasoning | 35% | Smart transaction matching + pattern detection in Python before LLM call |
| Safety & Escalation | 20% | Strict system prompt + post-processing validation layer |
| API Contract & Schema | 15% | Exact Pydantic schema + enum validation |
| Performance | 10% | Fast Groq API + async FastAPI |
| Response Quality | 10% | Well-crafted prompts with examples |
| Deployment | 5% | Docker image + live URL via ngrok/Railway |
| Documentation | 5% | Comprehensive README |

---

## Architecture

```
FastAPI App (main.py)
├── GET /health                    → 200 {"status":"ok"}
├── POST /analyze-ticket
│   ├── Input validation (Pydantic)
│   ├── Pre-analysis (Python rule engine)
│   │   ├── Transaction matching/scoring
│   │   ├── Pattern detection (duplicate, established recipient, etc.)
│   │   └── Language detection
│   ├── LLM call (Groq qwen3-27b)
│   │   ├── Structured JSON schema output
│   │   └── Safety-hardened system prompt
│   ├── Post-processing
│   │   ├── Safety guardrail validation
│   │   ├── Schema validation
│   │   └── Fallback rules
│   └── Response
└── Error handlers (400, 422, 500)
```

---

## Proposed Files

### [NEW] `app/main.py`
FastAPI app with all endpoints, error handlers, and lifespan.

### [NEW] `app/models.py`
Pydantic models for request/response schemas matching the API contract exactly.

### [NEW] `app/analyzer.py`
Core analysis engine:
- Pre-LLM rule-based analysis (transaction matching, pattern detection)
- Groq LLM call with structured output
- Post-processing safety validation

### [NEW] `app/prompts.py`
Carefully crafted system and user prompts with few-shot examples.

### [NEW] `app/safety.py`
Safety guardrail layer — validates `customer_reply` doesn't ask for credentials or make unauthorized promises.

### [NEW] `Dockerfile`
Lightweight Python 3.12 image, non-root user, port 8000.

### [NEW] `requirements.txt`
FastAPI, uvicorn, groq, pydantic, python-dotenv.

### [NEW] `README.md`
Full documentation: setup, run commands, AI models used, safety logic, limitations.

### [NEW] `.env.example`
Template showing required env vars.

### [NEW] `test_cases.py`
Script to test all 10 sample cases locally.

---

## Key Design Decisions

### 1. Transaction Matching (Rule-Based Pre-Processing)
Before calling the LLM, we run a rule-based engine to:
- Extract amounts and keywords from complaint text
- Score each transaction against the complaint
- Detect patterns: established recipient, near-duplicate timestamps, pending status
- Pass this structured context to the LLM

This boosts Evidence Reasoning score significantly.

### 2. Safety Guardrails (Two Layers)
**Layer 1 — System Prompt**: Strict instructions with banned phrases and required safety language.
**Layer 2 — Post-Processing**: Regex/keyword scan on `customer_reply` to catch any safety violations. If detected, replace with a safe fallback template.

### 3. Language Handling
- Detect complaint language (en/bn/mixed)
- Instruct LLM to reply in the same language as the complaint
- Bangla reply for Bangla complaints (Case 7 pattern)

### 4. Structured Output
Use Groq's `response_format` with `json_schema` to get perfectly structured responses from the model, then validate with Pydantic.

### 5. Performance
- FastAPI async endpoints
- Groq is extremely fast (p95 < 2s for this model)
- Connection timeout set to 25s (within 30s limit)

---

## Verification Plan

### Automated Tests
```bash
python test_cases.py  # Run all 10 sample cases
```

### Manual Verification
- Start server: `uvicorn app.main:app --reload`
- Test `/health`: `curl http://localhost:8000/health`
- Test `/analyze-ticket` with each sample case
- Verify Docker build: `docker build -t queuestorm . && docker run -p 8000:8000 --env-file .env queuestorm`
