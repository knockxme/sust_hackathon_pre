# SUST CSE Carnival 2026: Codex Community Hackathon
**Online Preliminary Round — Comprehensive Data Guide**

This document aggregates all information from the SUST CSE Carnival 2026 Preliminary Round documents, including the Problem Statement, Team Instructions Manual, Evaluation Rubric, and Public Sample Cases.

---

## 1. Problem Statement: QueueStorm Investigator

### 1.1 The Scenario
During a major digital finance platform's biggest campaign of the year, customer support agents are overwhelmed with complaints ranging from wrong transfers to phishing attempts. 
Teams must build an **AI/API service (QueueStorm Investigator)** to act as a copilot for support agents. It must read complaints, analyze the customer's transaction history, figure out what happened, decide who should handle it, and draft a safe reply without asking for sensitive credentials or promising unauthorized refunds.

### 1.2 The API Contract
Your service must expose the following HTTP endpoints:

| Method | Path | Required? | Purpose |
| :--- | :--- | :--- | :--- |
| **GET** | `/health` | Yes | Return `{"status":"ok"}` within 60 seconds of service start. Evaluates readiness. |
| **POST** | `/analyze-ticket` | Yes | Accepts one ticket JSON and returns a structured JSON response. Must respond within 30 seconds. |

**HTTP Response Codes:**
* **200:** Successful analysis matching the output schema.
* **400:** Malformed input (invalid JSON, missing fields).
* **422:** Schema valid, but semantically invalid (optional but encouraged).
* **500:** Internal error. No stack traces, tokens, or secrets should be exposed.

### 1.3 Request Schema (`POST /analyze-ticket`)

| Field | Type | Required? | Notes |
| :--- | :--- | :--- | :--- |
| `ticket_id` | string | **Yes** | Unique ticket identifier. Must be echoed in response. |
| `complaint` | string | **Yes** | Text in English, Bangla, or mixed Banglish. |
| `language` | string | Optional | `en`, `bn`, or `mixed` |
| `channel` | string | Optional | `in_app_chat`, `call_center`, `email`, `merchant_portal`, `field_agent` |
| `user_type` | string | Optional | `customer`, `merchant`, `agent`, `unknown` |
| `campaign_context` | string | Optional | Campaign identifier |
| `transaction_history` | array | Optional | List of recent transactions (2-5 entries). May be empty for safety cases. |
| `metadata` | object | Optional | Additional simulated context |

**Transaction History Entry:**
* `transaction_id` (string)
* `timestamp` (string - ISO 8601)
* `type` (string): `transfer`, `payment`, `cash_in`, `cash_out`, `settlement`, `refund`
* `amount` (number): BDT
* `counterparty` (string): Phone number, merchant ID, or agent ID
* `status` (string): `completed`, `failed`, `pending`, `reversed`

### 1.4 Response Schema

| Field | Type | Required? | Description |
| :--- | :--- | :--- | :--- |
| `ticket_id` | string | **Yes** | Must match request `ticket_id`. |
| `relevant_transaction_id` | string/null | **Yes** | Matching transaction ID, or `null` if none matches. |
| `evidence_verdict` | enum | **Yes** | `consistent`, `inconsistent`, `insufficient_data` |
| `case_type` | enum | **Yes** | (See Taxonomy Below) |
| `severity` | enum | **Yes** | `low`, `medium`, `high`, `critical` |
| `department` | enum | **Yes** | (See Taxonomy Below) |
| `agent_summary` | string | **Yes** | Concise agent-ready summary (1-2 sentences). |
| `recommended_next_action` | string | **Yes** | Suggested operational next step. |
| `customer_reply` | string | **Yes** | Safe official reply respecting all safety rules. |
| `human_review_required` | boolean | **Yes** | True for disputes, suspicious cases, high-value, or ambiguous. |
| `confidence` | number | Optional | Float between 0 and 1. |
| `reason_codes` | array | Optional | Short reason labels supporting the decision. |

### 1.5 Taxonomy and Enums

**`case_type` Enums:**
* `wrong_transfer`: Money sent to the wrong recipient.
* `payment_failed`: Transaction failed but balance may have been deducted.
* `refund_request`: Customer asking for a refund.
* `duplicate_payment`: Payment charged more than once.
* `merchant_settlement_delay`: Merchant settlement not received.
* `agent_cash_in_issue`: Cash deposit not reflected in balance.
* `phishing_or_social_engineering`: Suspicious requests for PIN/OTP.
* `other`: Anything not covered above.

**`department` Enums:**
* `customer_support`: `other`, low severity `refund_request`, vague cases.
* `dispute_resolution`: `wrong_transfer`, contested `refund_request`.
* `payments_ops`: `payment_failed`, `duplicate_payment`.
* `merchant_operations`: `merchant_settlement_delay`, merchant complaints.
* `agent_operations`: `agent_cash_in_issue`, agent side complaints.
* `fraud_risk`: `phishing_or_social_engineering`, suspicious activity.

---

## 2. Team Instructions Manual

### 2.1 Deployment Paths
Teams must submit at least ONE of the following:
1.  **Live URL (Strongly Recommended):** Public HTTPS base URL where endpoints are reachable.
2.  **Docker Image:** Public docker pull command + clear run command.
3.  **Code with runbook (Less preferred):** Complete step-by-step setup in a GitHub repo.

### 2.2 Docker Fallback Rules
* **Size:** Under 500MB recommended, 1GB hard limit.
* **Hardware:** No GPU allowed. Large local model weights or multi-GB runtime downloads are banned.
* **Port Binding:** Must bind to `0.0.0.0`.
* **Secrets:** Passed via environment variables only (`--env-file`). Never bake secrets into the image.

### 2.3 Secrets & External AI Policies
* **Rule-based logic** is allowed and encouraged. 
* **External APIs** (OpenAI, Anthropic, etc.) are allowed using the team's *own* keys.
* **Secret Handling:** NEVER commit API keys to GitHub (even private repos). Do not expose tokens in logs, `.env` files, or READMEs. 

### 2.4 Pre-Submit Checklist
- [ ] Endpoints tested (`/health` & `/analyze-ticket`).
- [ ] Schema matches EXACTLY (including enum cases).
- [ ] Safety guardrails verified against OTP/PIN/Refund tests.
- [ ] `README.md` includes setup, run command, AI models used, safety logic, and limitations.
- [ ] NO real secrets committed to the repository.

---

## 3. Evaluation Rubric & Safety Penalties

The evaluation has two stages: **Stage 1 (Automated API tests)** for all teams, and **Stage 2 (Manual Review)** for shortlisted teams.

### 3.1 The Seven Scoring Categories

| Category | Weight | Stage | What it measures |
| :--- | :--- | :--- | :--- |
| **1. Evidence Reasoning** | 35 | Automated | Policy-based scoring for transaction matching, verdict, case routing. |
| **2. Safety & Escalation** | 20 | Auto + Manual | Checks avoidance of credential requests and unsafe refund promises. |
| **3. API Contract & Schema** | 15 | Automated | Valid JSON, required fields, correct types, enums, status codes. |
| **4. Performance & Reliability** | 10 | Auto + Manual | Timeout rate (<30s), p95 latency (<=5s ideal), failure/crash handling. |
| **5. Response Quality** | 10 | Manual | Useful text: clear summary, practical next action, professional reply. |
| **6. Deployment** | 5 | Auto + Manual | Can judges run/reach the service without team help? |
| **7. Documentation** | 5 | Manual | README explains setup, AI used, safety logic, limits. |

### 3.2 Safety Penalties (Critical Guardrails)

| Violation | Penalty | Explanation |
| :--- | :--- | :--- |
| **Asks for PIN, OTP, password, full card number** | **-15 points** | The system must never request credentials. |
| **Confirms refund, reversal, or recovery without authority** | **-10 points** | Cannot promise financial action (use "eligible amounts will be returned"). |
| **Directs customer to suspicious 3rd parties** | **-10 points** | Must guide users to official support channels only. |
| **2+ critical safety violations** | **Disqualification** | Not eligible for the top-40 finalist pool. |

### 3.3 Tie-Breakers
1. Safety score and absence of critical violations.
2. Evidence reasoning score.
3. API/schema validity.
4. API reliability & deployment stability.
5. Exceptional integration/architecture.
6. Bangla/Banglish handling quality.
7. Documentation quality.
8. 90-second architecture video.

---

## 4. Public Sample Cases Pack

*(Metadata: Ten fully worked sample cases showing the expected input and output shape for POST /analyze-ticket.)*

### Case 1: SAMPLE-01 — Wrong transfer with matching evidence

**Input Request:**
```json
{
  "ticket_id": "TKT-001",
  "complaint": "I sent 5000 taka to a wrong number around 2pm today. The number was supposed to be 01712345678 but I think I typed it wrong. The person isn't responding to my call. Please help me get my money back.",
  "language": "en",
  "channel": "in_app_chat",
  "user_type": "customer",
  "campaign_context": "boishakh_bonanza_day_1",
  "transaction_history": [
    {
      "transaction_id": "TXN-9101",
      "timestamp": "2026-04-14T14:08:22Z",
      "type": "transfer",
      "amount": 5000,
      "counterparty": "+8801719876543",
      "status": "completed"
    },
    {
      "transaction_id": "TXN-9087",
      "timestamp": "2026-04-13T18:12:00Z",
      "type": "cash_in",
      "amount": 10000,
      "counterparty": "AGENT-512",
      "status": "completed"
    }
  ]
}
```

**Expected Output:**
```json
{
  "ticket_id": "TKT-001",
  "relevant_transaction_id": "TXN-9101",
  "evidence_verdict": "consistent",
  "case_type": "wrong_transfer",
  "severity": "high",
  "department": "dispute_resolution",
  "agent_summary": "Customer reports sending 5000 BDT via TXN-9101 to +8801719876543, which they now believe was the wrong recipient. Recipient is unresponsive.",
  "recommended_next_action": "Verify TXN-9101 details with the customer and initiate the wrong-transfer dispute workflow per policy.",
  "customer_reply": "We have noted your concern about transaction TXN-9101. Please do not share your PIN or OTP with anyone. Our dispute team will review the case and contact you through official support channels.",
  "human_review_required": true,
  "confidence": 0.9,
  "reason_codes": [
    "wrong_transfer",
    "transaction_match",
    "dispute_initiated"
  ]
}
```

**Rationale:** Complaint amount (5000) and approximate time (2pm) align cleanly with TXN-9101. This is the canonical wrong-transfer dispute path: identify the transaction, route to dispute_resolution, escalate for human review, and keep the customer_reply safe (no refund promises).

---

### Case 2: SAMPLE-02 — Wrong transfer claim with inconsistent evidence

**Input Request:**
```json
{
  "ticket_id": "TKT-002",
  "complaint": "I sent 2000 to the wrong person by mistake. Please reverse it.",
  "language": "en",
  "channel": "in_app_chat",
  "user_type": "customer",
  "transaction_history": [
    {
      "transaction_id": "TXN-9202",
      "timestamp": "2026-04-14T11:30:00Z",
      "type": "transfer",
      "amount": 2000,
      "counterparty": "+8801812345678",
      "status": "completed"
    },
    {
      "transaction_id": "TXN-9180",
      "timestamp": "2026-04-10T09:15:00Z",
      "type": "transfer",
      "amount": 2500,
      "counterparty": "+8801812345678",
      "status": "completed"
    },
    {
      "transaction_id": "TXN-9145",
      "timestamp": "2026-04-05T17:45:00Z",
      "type": "transfer",
      "amount": 1500,
      "counterparty": "+8801812345678",
      "status": "completed"
    }
  ]
}
```

**Expected Output:**
```json
{
  "ticket_id": "TKT-002",
  "relevant_transaction_id": "TXN-9202",
  "evidence_verdict": "inconsistent",
  "case_type": "wrong_transfer",
  "severity": "medium",
  "department": "dispute_resolution",
  "agent_summary": "Customer claims TXN-9202 (2000 BDT to +8801812345678) was a wrong transfer, but transaction history shows three prior transfers to the same counterparty in the past nine days, suggesting an established recipient.",
  "recommended_next_action": "Flag for human review. Verify with the customer whether this was genuinely a wrong transfer given the established transaction pattern with this recipient.",
  "customer_reply": "We have received your request regarding transaction TXN-9202. Please do not share your PIN or OTP with anyone. Our dispute team will review the case carefully and contact you through official support channels.",
  "human_review_required": true,
  "confidence": 0.75,
  "reason_codes": [
    "wrong_transfer_claim",
    "established_recipient_pattern",
    "evidence_inconsistent"
  ]
}
```

**Rationale:** Repeated past transfers to the same recipient contradict the wrong transfer claim. The service correctly identifies the relevant transaction (the most recent one of matching amount) but flags the inconsistency for human review rather than rubber-stamping the dispute.

---

### Case 3: SAMPLE-03 — Failed payment with balance deducted

**Input Request:**
```json
{
  "ticket_id": "TKT-003",
  "complaint": "I tried to pay 1200 taka for my mobile recharge but the app showed failed. But my balance was deducted! Please refund my money.",
  "language": "en",
  "channel": "in_app_chat",
  "user_type": "customer",
  "transaction_history": [
    {
      "transaction_id": "TXN-9301",
      "timestamp": "2026-04-14T16:00:00Z",
      "type": "payment",
      "amount": 1200,
      "counterparty": "MERCHANT-MOBILE-OP",
      "status": "failed"
    }
  ]
}
```

**Expected Output:**
```json
{
  "ticket_id": "TKT-003",
  "relevant_transaction_id": "TXN-9301",
  "evidence_verdict": "consistent",
  "case_type": "payment_failed",
  "severity": "high",
  "department": "payments_ops",
  "agent_summary": "Customer attempted a 1200 BDT mobile recharge (TXN-9301) which failed, but reports balance was deducted. Requires payments operations investigation.",
  "recommended_next_action": "Investigate TXN-9301 ledger status. If balance was deducted on a failed payment, initiate the automatic reversal flow within standard SLA.",
  "customer_reply": "We have noted that transaction TXN-9301 may have caused an unexpected balance deduction. Our payments team will review the case and any eligible amount will be returned through official channels. Please do not share your PIN or OTP with anyone.",
  "human_review_required": false,
  "confidence": 0.9,
  "reason_codes": [
    "payment_failed",
    "potential_balance_deduction"
  ]
}
```

**Rationale:** Clear payment failure with claimed balance deduction. Routes to payments_ops. Note the customer_reply does NOT promise a refund. It says 'any eligible amount will be returned through official channels', which is safe language.

---

### Case 4: SAMPLE-04 — Refund request requiring safe handling

**Input Request:**
```json
{
  "ticket_id": "TKT-004",
  "complaint": "I paid 500 to a merchant for a product but I changed my mind and don't want it anymore. Please refund my 500 taka.",
  "language": "en",
  "channel": "in_app_chat",
  "user_type": "customer",
  "transaction_history": [
    {
      "transaction_id": "TXN-9401",
      "timestamp": "2026-04-14T13:00:00Z",
      "type": "payment",
      "amount": 500,
      "counterparty": "MERCHANT-7821",
      "status": "completed"
    }
  ]
}
```

**Expected Output:**
```json
{
  "ticket_id": "TKT-004",
  "relevant_transaction_id": "TXN-9401",
  "evidence_verdict": "consistent",
  "case_type": "refund_request",
  "severity": "low",
  "department": "customer_support",
  "agent_summary": "Customer requests refund of 500 BDT for TXN-9401 (merchant payment) due to change of mind. Not a service failure.",
  "recommended_next_action": "Inform the customer that refund eligibility depends on the merchant's own policy. Provide guidance on contacting the merchant directly for a refund.",
  "customer_reply": "Thank you for reaching out. Refunds for completed merchant payments depend on the merchant's own policy. We recommend contacting the merchant directly. If you need help reaching them, please reply and we will guide you. Please do not share your PIN or OTP with anyone.",
  "human_review_required": false,
  "confidence": 0.85,
  "reason_codes": [
    "refund_request",
    "merchant_policy_dependent"
  ]
}
```

**Rationale:** The service must NOT promise a refund it cannot authorize. It correctly identifies the case, routes to customer_support, and gives the customer accurate next steps without overcommitting. A response that says 'we will refund you' would trigger the -10 unauthorized refund penalty.

---

### Case 5: SAMPLE-05 — Phishing or social engineering report

**Input Request:**
```json
{
  "ticket_id": "TKT-005",
  "complaint": "Someone called me saying they are from bKash and asked for my OTP. They said my account will be blocked if I don't share it. Is this real? I haven't shared anything yet.",
  "language": "en",
  "channel": "call_center",
  "user_type": "customer",
  "transaction_history": []
}
```

**Expected Output:**
```json
{
  "ticket_id": "TKT-005",
  "relevant_transaction_id": null,
  "evidence_verdict": "insufficient_data",
  "case_type": "phishing_or_social_engineering",
  "severity": "critical",
  "department": "fraud_risk",
  "agent_summary": "Customer reports an unsolicited call claiming to be from the company and asking for OTP. Customer has not yet shared credentials. Likely social engineering attempt.",
  "recommended_next_action": "Escalate to fraud_risk team immediately. Confirm to customer that the company never asks for OTP. Log the reported number for fraud pattern analysis.",
  "customer_reply": "Thank you for reaching out before sharing any information. We never ask for your PIN, OTP, or password under any circumstances. Please do not share these with anyone, even if they claim to be from us. Our fraud team has been notified of this incident.",
  "human_review_required": true,
  "confidence": 0.95,
  "reason_codes": [
    "phishing",
    "credential_protection",
    "critical_escalation"
  ]
}
```

**Rationale:** Phishing reports are critical severity by default. Note the customer_reply explicitly reinforces the credential safety rule, thanks the customer for caution, and does not attempt to verify the caller's identity (which would itself be unsafe). Empty transaction_history is normal for safety reports.

---

### Case 6: SAMPLE-06 — Vague complaint, insufficient evidence

**Input Request:**
```json
{
  "ticket_id": "TKT-006",
  "complaint": "Something is wrong with my money. Please check.",
  "language": "en",
  "channel": "in_app_chat",
  "user_type": "customer",
  "transaction_history": [
    {
      "transaction_id": "TXN-9601",
      "timestamp": "2026-04-13T10:00:00Z",
      "type": "cash_in",
      "amount": 3000,
      "counterparty": "AGENT-220",
      "status": "completed"
    },
    {
      "transaction_id": "TXN-9602",
      "timestamp": "2026-04-12T15:30:00Z",
      "type": "transfer",
      "amount": 800,
      "counterparty": "+8801911223344",
      "status": "completed"
    }
  ]
}
```

**Expected Output:**
```json
{
  "ticket_id": "TKT-006",
  "relevant_transaction_id": null,
  "evidence_verdict": "insufficient_data",
  "case_type": "other",
  "severity": "low",
  "department": "customer_support",
  "agent_summary": "Customer reports a vague concern about their money without specifying transaction, amount, or issue. Insufficient detail to identify any relevant transaction.",
  "recommended_next_action": "Reply to customer asking for specific details: which transaction, what amount, what went wrong, and approximate time.",
  "customer_reply": "Thank you for reaching out. To help you faster, please share the transaction ID, the amount involved, and a short description of what went wrong. Please do not share your PIN or OTP with anyone.",
  "human_review_required": false,
  "confidence": 0.6,
  "reason_codes": [
    "vague_complaint",
    "needs_clarification"
  ]
}
```

**Rationale:** Without specifics, the service should not guess. It returns insufficient_data, asks for clarification politely, and does not flag for human review yet. Guessing a transaction here would risk an unnecessary dispute on a transaction the customer is not actually worried about.

---

### Case 7: SAMPLE-07 — Agent cash-in issue, Bangla complaint

**Input Request:**
```json
{
  "ticket_id": "TKT-007",
  "complaint": "আমি আজ সকালে এজেন্টের কাছে ২০০০ টাকা ক্যাশ ইন করেছি কিন্তু আমার ব্যালেন্সে টাকা আসেনি। এজেন্ট বলছে টাকা পাঠিয়েছে কিন্তু আমি দেখছি না।",
  "language": "bn",
  "channel": "call_center",
  "user_type": "customer",
  "transaction_history": [
    {
      "transaction_id": "TXN-9701",
      "timestamp": "2026-04-14T09:30:00Z",
      "type": "cash_in",
      "amount": 2000,
      "counterparty": "AGENT-318",
      "status": "pending"
    }
  ]
}
```

**Expected Output:**
```json
{
  "ticket_id": "TKT-007",
  "relevant_transaction_id": "TXN-9701",
  "evidence_verdict": "consistent",
  "case_type": "agent_cash_in_issue",
  "severity": "high",
  "department": "agent_operations",
  "agent_summary": "Customer reports 2000 BDT cash-in via AGENT-318 (TXN-9701) not reflected in balance. Transaction status is pending. Agent claims funds were sent.",
  "recommended_next_action": "Investigate TXN-9701 pending status with agent operations. Confirm settlement state and resolve within the standard cash-in SLA.",
  "customer_reply": "আপনার লেনদেন TXN-9701 এর বিষয়ে আমরা অবগত হয়েছি। আমাদের এজেন্ট অপারেশন্স দল এটি দ্রুত যাচাই করবে এবং অফিসিয়াল চ্যানেলে আপনাকে জানাবে। অনুগ্রহ করে কারো সাথে আপনার পিন বা ওটিপি শেয়ার করবেন না।",
  "human_review_required": true,
  "confidence": 0.88,
  "reason_codes": [
    "agent_cash_in",
    "pending_transaction",
    "agent_ops"
  ]
}
```

**Rationale:** Bangla input is handled natively. The customer_reply is returned in the same language (Bangla) as the input. Pending status combined with the customer's claim of non-receipt warrants human review and agent_operations investigation.

---

### Case 8: SAMPLE-08 — Multiple plausible transactions, ambiguous match

**Input Request:**
```json
{
  "ticket_id": "TKT-008",
  "complaint": "I sent 1000 to my brother yesterday but he says he didn't get it. Please check.",
  "language": "en",
  "channel": "in_app_chat",
  "user_type": "customer",
  "transaction_history": [
    {
      "transaction_id": "TXN-9801",
      "timestamp": "2026-04-13T11:20:00Z",
      "type": "transfer",
      "amount": 1000,
      "counterparty": "+8801712001122",
      "status": "completed"
    },
    {
      "transaction_id": "TXN-9802",
      "timestamp": "2026-04-13T19:45:00Z",
      "type": "transfer",
      "amount": 1000,
      "counterparty": "+8801812334455",
      "status": "completed"
    },
    {
      "transaction_id": "TXN-9803",
      "timestamp": "2026-04-13T20:10:00Z",
      "type": "transfer",
      "amount": 1000,
      "counterparty": "+8801712001122",
      "status": "failed"
    }
  ]
}
```

**Expected Output:**
```json
{
  "ticket_id": "TKT-008",
  "relevant_transaction_id": null,
  "evidence_verdict": "insufficient_data",
  "case_type": "wrong_transfer",
  "severity": "medium",
  "department": "dispute_resolution",
  "agent_summary": "Customer reports a 1000 BDT transfer to their brother was not received. Three transactions of 1000 BDT exist on the date in question (two completed, one failed) to two different recipients. Cannot determine which is the brother's number without further input.",
  "recommended_next_action": "Reply to customer asking for the brother's number to identify the correct transaction. Do not initiate dispute until the transaction is confirmed.",
  "customer_reply": "Thank you for reaching out. We see multiple transactions of 1000 BDT on that date. Could you share your brother's number so we can identify the right transaction? Please do not share your PIN or OTP with anyone.",
  "human_review_required": false,
  "confidence": 0.65,
  "reason_codes": [
    "ambiguous_match",
    "needs_clarification"
  ]
}
```

**Rationale:** When multiple transactions plausibly match, do not guess. Return insufficient_data, ask for the disambiguating detail (the brother's number), and avoid initiating any dispute prematurely. Picking one transaction here at random would risk an incorrect dispute.

---

### Case 9: SAMPLE-09 — Merchant settlement delay

**Input Request:**
```json
{
  "ticket_id": "TKT-009",
  "complaint": "I am a merchant. My yesterday's sales of 15000 taka have not been settled to my account. Settlement usually happens by 11am next day. Please check.",
  "language": "en",
  "channel": "merchant_portal",
  "user_type": "merchant",
  "transaction_history": [
    {
      "transaction_id": "TXN-9901",
      "timestamp": "2026-04-13T18:00:00Z",
      "type": "settlement",
      "amount": 15000,
      "counterparty": "MERCHANT-SELF",
      "status": "pending"
    }
  ]
}
```

**Expected Output:**
```json
{
  "ticket_id": "TKT-009",
  "relevant_transaction_id": "TXN-9901",
  "evidence_verdict": "consistent",
  "case_type": "merchant_settlement_delay",
  "severity": "medium",
  "department": "merchant_operations",
  "agent_summary": "Merchant reports yesterday's 15000 BDT settlement (TXN-9901) is delayed beyond the standard 11 AM next-day window. Settlement status is pending.",
  "recommended_next_action": "Route to merchant_operations to verify settlement batch status. If the batch is delayed, communicate a revised ETA to the merchant.",
  "customer_reply": "We have noted your concern about settlement TXN-9901. Our merchant operations team will check the batch status and update you on the expected settlement time through official channels.",
  "human_review_required": false,
  "confidence": 0.92,
  "reason_codes": [
    "merchant_settlement",
    "delay",
    "pending"
  ]
}
```

**Rationale:** Merchant-side complaint with clear evidence of a pending settlement. Routes to merchant_operations. Note that user_type='merchant' should influence routing and response tone. The customer_reply here is more business-formal than the customer-facing replies in other cases.

---

### Case 10: SAMPLE-10 — Duplicate payment claim

**Input Request:**
```json
{
  "ticket_id": "TKT-010",
  "complaint": "I paid my electricity bill 850 taka but it deducted twice from my account. Please check, I only paid once.",
  "language": "en",
  "channel": "in_app_chat",
  "user_type": "customer",
  "transaction_history": [
    {
      "transaction_id": "TXN-10001",
      "timestamp": "2026-04-14T08:15:30Z",
      "type": "payment",
      "amount": 850,
      "counterparty": "BILLER-DESCO",
      "status": "completed"
    },
    {
      "transaction_id": "TXN-10002",
      "timestamp": "2026-04-14T08:15:42Z",
      "type": "payment",
      "amount": 850,
      "counterparty": "BILLER-DESCO",
      "status": "completed"
    }
  ]
}
```

**Expected Output:**
```json
{
  "ticket_id": "TKT-010",
  "relevant_transaction_id": "TXN-10002",
  "evidence_verdict": "consistent",
  "case_type": "duplicate_payment",
  "severity": "high",
  "department": "payments_ops",
  "agent_summary": "Customer reports duplicate electricity bill payment. Two identical 850 BDT payments to BILLER-DESCO were completed 12 seconds apart (TXN-10001 and TXN-10002). The second is likely the duplicate.",
  "recommended_next_action": "Verify the duplicate with payments_ops. If the biller confirms only one payment was received, initiate reversal of TXN-10002.",
  "customer_reply": "We have noted the possible duplicate payment for transaction TXN-10002. Our payments team will verify with the biller and any eligible amount will be returned through official channels. Please do not share your PIN or OTP with anyone.",
  "human_review_required": true,
  "confidence": 0.93,
  "reason_codes": [
    "duplicate_payment",
    "biller_verification_required"
  ]
}
```

**Rationale:** Two identical payments within 12 seconds strongly indicate a duplicate. The relevant_transaction_id should point to the suspected duplicate (the second one), not the first. The customer_reply carefully avoids promising the refund: it says 'any eligible amount will be returned', which is safe language.

---

