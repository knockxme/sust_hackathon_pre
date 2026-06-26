# QueueStorm Investigator 🚀

**AI-powered support ticket analysis copilot for digital finance platforms.**

Built for the **SUST CSE Carnival 2026 — Codex Community Hackathon** (Online Preliminary Round).

---

## What It Does

QueueStorm Investigator acts as an intelligent copilot for customer support agents. Given a customer complaint (in English, Bangla, or Banglish) and optional transaction history, it:

1. **Classifies the case** — wrong transfer, payment failure, phishing, duplicate payment, etc.
2. **Matches transaction evidence** — finds the relevant transaction and evaluates if the evidence is consistent with the complaint
3. **Routes to the right team** — dispute_resolution, fraud_risk, payments_ops, etc.
4. **Drafts a safe customer reply** — never asks for credentials, never promises unauthorized refunds

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Returns `{"status": "ok"}` — liveness probe |
| `POST` | `/analyze-ticket` | Analyzes a support ticket, returns structured JSON |

Interactive docs available at `/docs` (Swagger UI) and `/redoc`.

---

## Quick Start

### Prerequisites
- Python 3.12+
- A Groq API key (set via environment variable)

### 1. Clone & Install

```bash
git clone <your-repo-url>
cd SUST_Hackathon_Pre_Solve-main

pip install -r requirements.txt
```

### 2. Set Environment Variable

```bash
# Copy the template
cp .env.example .env

# Edit .env and add your key:
# GROQ_API_KEY=your_groq_api_key_here
```

> ⚠️ Never commit your `.env` file. It is listed in `.gitignore`.

### 3. Run the Server

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Server starts at: `http://localhost:8000`

### 4. Test It

```bash
# Health check
curl http://localhost:8000/health

# Analyze a ticket
curl -X POST http://localhost:8000/analyze-ticket \
  -H "Content-Type: application/json" \
  -d '{
    "ticket_id": "TKT-001",
    "complaint": "I sent 5000 taka to a wrong number around 2pm today. Please help.",
    "language": "en",
    "channel": "in_app_chat",
    "user_type": "customer",
    "transaction_history": [
      {
        "transaction_id": "TXN-9101",
        "timestamp": "2026-04-14T14:08:22Z",
        "type": "transfer",
        "amount": 5000,
        "counterparty": "+8801719876543",
        "status": "completed"
      }
    ]
  }'

# Run all 10 sample cases
python test_cases.py
```

---

## Docker Deployment

### Build

```bash
docker build -t queuestorm-investigator .
```

### Run

```bash
docker run -p 8000:8000 --env-file .env queuestorm-investigator
```

Or pass the key directly:

```bash
docker run -p 8000:8000 -e GROQ_API_KEY=your_key_here queuestorm-investigator
```

The service binds to `0.0.0.0:8000` and is immediately reachable.

---

## Architecture

```
POST /analyze-ticket
        │
        ▼
┌─────────────────────────────────────────────┐
│  Phase 1: Rule-Based Pre-Analysis (Python)  │
│  ─────────────────────────────────────────  │
│  • Extract amounts from complaint text      │
│  • Detect phishing/fraud keywords           │
│  • Score each transaction vs. complaint     │
│  • Detect duplicate payment patterns        │
│  • Detect established recipient patterns    │
│  • Flag pending transactions                │
└──────────────────┬──────────────────────────┘
                   │ Structured context hints
                   ▼
┌─────────────────────────────────────────────┐
│  Phase 2: LLM Analysis (Groq qwen3-27b)     │
│  ─────────────────────────────────────────  │
│  • Safety-hardened system prompt            │
│  • Few-shot examples for accuracy           │
│  • Structured JSON output (json_schema)     │
│  • Pydantic-validated response              │
└──────────────────┬──────────────────────────┘
                   │ LLM analysis result
                   ▼
┌─────────────────────────────────────────────┐
│  Phase 3: Safety Validation & Repair        │
│  ─────────────────────────────────────────  │
│  • Scan customer_reply for safety violations│
│  • Replace with safe fallback if needed     │
│  • Ensure PIN/OTP reminder present          │
│  • Final enum + schema validation           │
└──────────────────┬──────────────────────────┘
                   │
                   ▼
         Structured JSON Response
```

---

## AI Models Used

| Model | Provider | Purpose |
|---|---|---|
| `qwen/qwen3.6-27b` | [Groq](https://groq.com) | Primary ticket analysis — reasoning model with chain-of-thought |
| `meta-llama/llama-4-scout-17b-16e-instruct` | [Groq](https://groq.com) | Structured output fallback with `json_schema` enforcement |

**Model Strategy**: We call `qwen/qwen3.6-27b` first for its superior reasoning capability (it uses chain-of-thought `<think>` tags before outputting JSON). If parsing fails, we automatically fall back to `llama-4-scout` which natively supports `json_schema` structured output. This gives us both reasoning quality AND output reliability.

---

## Safety Logic

Safety is the highest-priority concern. We implement **two independent safety layers**:

### Layer 1 — System Prompt Guardrails
The LLM system prompt explicitly prohibits:
- Asking for PIN, OTP, password, or card numbers
- Promising refunds, reversals, or account unblocks without authority
- Directing customers to unofficial third parties

Safe language templates are provided: `"any eligible amount will be returned through official channels"`

### Layer 2 — Post-Processing Safety Validator (`app/safety.py`)
After every LLM response, we:
1. Scan `customer_reply` with regex patterns for all violation types
2. If any violation is found → **replace entire reply** with a case-type-specific safe fallback template
3. Ensure every reply contains the required PIN/OTP safety reminder
4. All violations are logged for monitoring

This guarantees zero safety violations even if the LLM misbehaves.

---

## Supported Case Types

| Case Type | Department | Typical Severity |
|---|---|---|
| `wrong_transfer` | `dispute_resolution` | high |
| `payment_failed` | `payments_ops` | high |
| `refund_request` | `customer_support` | low |
| `duplicate_payment` | `payments_ops` | high |
| `merchant_settlement_delay` | `merchant_operations` | medium |
| `agent_cash_in_issue` | `agent_operations` | high |
| `phishing_or_social_engineering` | `fraud_risk` | critical |
| `other` | `customer_support` | low |

---

## Multilingual Support

- **English (en)**: Full support
- **Bangla (বাংলা, bn)**: Complaint analysis + reply in Bangla
- **Mixed Banglish (mixed)**: Complaint analysis + English reply

The system prompt explicitly instructs the LLM to respond in the same language as the complaint.

---

## Error Handling

| Status | Meaning |
|---|---|
| `200` | Successful analysis |
| `400` | Malformed request (missing required fields, invalid JSON) |
| `422` | Schema-valid but semantically invalid |
| `500` | Internal error (no stack traces or secrets exposed) |

---

## Performance

- **Target**: p95 latency ≤ 5 seconds (Groq is typically 1-3s)
- **Hard limit**: 30 seconds per request
- **Timeout**: LLM call set to 25s, leaving buffer
- **Fallback**: If LLM fails, rule-based fallback returns a valid, safe response

---

## Project Structure

```
.
├── app/
│   ├── __init__.py
│   ├── main.py          # FastAPI app, endpoints, error handlers
│   ├── models.py        # Pydantic schemas (request, response, LLM output)
│   ├── analyzer.py      # Core analysis engine (rule-based + LLM)
│   ├── prompts.py       # System & user prompt templates
│   └── safety.py        # Safety validation & repair layer
├── Dockerfile           # Production Docker image
├── requirements.txt     # Python dependencies
├── test_cases.py        # Test runner for all 10 sample cases
├── .env.example         # Environment variable template
├── .gitignore           # Prevents secrets from being committed
└── README.md            # This file
```

---

## Limitations

1. The service uses an external LLM API (Groq). If the API is unavailable, the service falls back to rule-based analysis which may have lower accuracy on complex cases.
2. Transaction history is analyzed in the context of the complaint only — the service does not have access to the full account history beyond what is provided.
3. Bangla complaint analysis relies on the LLM's multilingual capability. Very colloquial or regional Bangla dialects may have slightly lower accuracy.
4. Amount extraction from Banglish ("panchshoy taka" = "500 taka") is not supported — the system works best with numeric amounts.

---

## Pre-Submit Checklist

- [x] `GET /health` returns `{"status": "ok"}` within 60s of start
- [x] `POST /analyze-ticket` responds within 30s
- [x] All required response fields present with correct types
- [x] All enum values match the specification exactly
- [x] `customer_reply` never asks for credentials
- [x] `customer_reply` never promises unauthorized refunds
- [x] Safety tested against phishing and credential-ask edge cases
- [x] Bangla complaint handling verified (Case 7)
- [x] Docker image builds and runs successfully
- [x] No real secrets committed to repository
- [x] README complete with setup, AI models, safety logic, limitations
