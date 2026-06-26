from __future__ import annotations

"""
Core analysis engine for QueueStorm Investigator.

Two-phase analysis:
  Phase 1: Rule-based pre-processing (fast, deterministic)
    - Extract amounts/keywords from complaint
    - Score transactions against complaint
    - Detect patterns (duplicate, established recipient, phishing)
    - Build structured context hints

  Phase 2: LLM call (Groq qwen3-27b)
    - Structured JSON schema output via Groq response_format
    - Uses pre-analysis context for better accuracy
    - Post-processing safety validation
"""

import os
import re
import json
import logging
from datetime import datetime, timezone
from typing import Optional
from collections import Counter

from groq import Groq
from pydantic import ValidationError

from app.models import (
    AnalyzeTicketRequest,
    AnalyzeTicketResponse,
    LLMTicketAnalysis,
    EvidenceVerdict,
    CaseType,
    Severity,
    Department,
    Language,
)
from app.prompts import SYSTEM_PROMPT, build_user_prompt
from app.safety import validate_and_repair_reply, get_safe_fallback_reply

logger = logging.getLogger(__name__)

# ─── Groq Client ───────────────────────────────────────────────────────────────

def get_groq_client() -> Groq:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY environment variable not set")
    return Groq(api_key=api_key)


# ─── Phishing & Fraud Keywords ─────────────────────────────────────────────────

PHISHING_KEYWORDS_EN = [
    "otp", "pin", "password", "account will be blocked", "account blocked",
    "share your otp", "share otp", "share pin", "verify your account",
    "calling from", "from bkash", "from bank", "from company",
    "suspicious activity", "unauthorized access", "account hacked",
    "send otp", "give otp", "provide otp",
]

PHISHING_KEYWORDS_BN = [
    "ওটিপি", "পিন", "পাসওয়ার্ড", "একাউন্ট বন্ধ", "ব্লক",
    "শেয়ার করুন", "যাচাই করুন", "বিকাশ থেকে",
]

# Amount extraction patterns
AMOUNT_PATTERNS = [
    r"(\d[\d,]*)\s*(?:taka|tk|bdt|টাকা|৳)",
    r"(?:taka|tk|bdt|টাকা|৳)\s*(\d[\d,]*)",
    r"\b(\d{3,6})\b",  # Bare numbers that look like amounts
]

# Time extraction patterns
TIME_PATTERNS = [
    r"\b(2\s*pm|2pm|14:00|afternoon)\b",
    r"\b(morning|সকাল)\b",
    r"\b(yesterday|গতকাল)\b",
    r"\b(today|আজ)\b",
    r"\b(\d{1,2}\s*(?:am|pm))\b",
    r"\b(\d{1,2}:\d{2})\b",
]


# ─── Phase 1: Rule-Based Pre-Analysis ─────────────────────────────────────────

def extract_amounts_from_complaint(complaint: str) -> list[float]:
    """Extract monetary amounts mentioned in the complaint."""
    amounts = []
    text = complaint.lower()

    for pattern in AMOUNT_PATTERNS:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for m in matches:
            try:
                # Remove commas
                val = float(m.replace(",", ""))
                if 1 <= val <= 10_000_000:  # Reasonable BDT range
                    amounts.append(val)
            except (ValueError, AttributeError):
                pass

    return list(set(amounts))


def detect_phishing_signals(complaint: str) -> list[str]:
    """Detect phishing/social engineering keywords in complaint."""
    signals = []
    complaint_lower = complaint.lower()

    for kw in PHISHING_KEYWORDS_EN:
        if kw in complaint_lower:
            signals.append(kw)

    for kw in PHISHING_KEYWORDS_BN:
        if kw in complaint:
            signals.append(kw)

    return signals


def detect_case_type_hint(complaint: str, user_type: str = "customer") -> Optional[str]:
    """Rule-based case type hint from complaint text."""
    complaint_lower = complaint.lower()

    phishing_signals = detect_phishing_signals(complaint)
    if phishing_signals:
        return "phishing_or_social_engineering"

    if user_type == "merchant":
        if any(kw in complaint_lower for kw in ["settlement", "not settled", "not received", "সেটেলমেন্ট"]):
            return "merchant_settlement_delay"

    if any(kw in complaint_lower for kw in ["cash in", "cash-in", "ক্যাশ ইন", "agent", "এজেন্ট"]):
        if any(kw in complaint_lower for kw in ["not received", "not reflect", "আসেনি", "দেখছি না", "balance"]):
            return "agent_cash_in_issue"

    if any(kw in complaint_lower for kw in ["twice", "double", "duplicate", "deducted twice", "charged twice", "দুইবার"]):
        return "duplicate_payment"

    if any(kw in complaint_lower for kw in ["failed", "not success", "unsuccessful", "declined", "ব্যর্থ"]):
        if any(kw in complaint_lower for kw in ["deducted", "balance", "money"]):
            return "payment_failed"

    if any(kw in complaint_lower for kw in ["wrong", "wrong number", "mistake", "wrong person", "ভুল"]):
        return "wrong_transfer"

    if any(kw in complaint_lower for kw in ["refund", "money back", "return", "ফেরত"]):
        return "refund_request"

    return None


def score_transaction_match(
    txn: dict,
    complaint_amounts: list[float],
    complaint_lower: str,
    complaint_type_hint: Optional[str],
) -> float:
    """
    Score how well a transaction matches the complaint.
    Higher = better match.
    """
    score = 0.0

    # Amount match (strongest signal)
    txn_amount = txn.get("amount", 0)
    for amt in complaint_amounts:
        if abs(txn_amount - amt) < 1:  # Exact match
            score += 50
        elif abs(txn_amount - amt) / max(amt, 1) < 0.05:  # Within 5%
            score += 30

    # Type match
    txn_type = txn.get("type", "")
    type_keywords = {
        "transfer": ["transfer", "sent", "send", "wrong number", "ভুল", "পাঠিয়েছি"],
        "payment": ["payment", "paid", "bill", "recharge", "merchant", "পেমেন্ট"],
        "cash_in": ["cash in", "cash-in", "ক্যাশ ইন", "deposit"],
        "cash_out": ["cash out", "withdraw", "ক্যাশ আউট"],
        "settlement": ["settlement", "সেটেলমেন্ট"],
        "refund": ["refund", "return", "ফেরত"],
    }
    for kw in type_keywords.get(txn_type, []):
        if kw in complaint_lower:
            score += 20
            break

    # Status clues
    status = txn.get("status", "")
    if status == "failed" and any(kw in complaint_lower for kw in ["failed", "not success", "ব্যর্থ"]):
        score += 15
    if status == "pending" and any(kw in complaint_lower for kw in ["pending", "not received", "আসেনি"]):
        score += 15

    # Time-related clues
    timestamp_str = txn.get("timestamp", "")
    if timestamp_str:
        try:
            txn_dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            hours_ago = (now - txn_dt).total_seconds() / 3600

            if "today" in complaint_lower or "আজ" in complaint_lower:
                if hours_ago <= 24:
                    score += 10
            if "yesterday" in complaint_lower or "গতকাল" in complaint_lower:
                if 24 <= hours_ago <= 48:
                    score += 10
            if "morning" in complaint_lower or "সকাল" in complaint_lower:
                if 6 <= txn_dt.hour <= 12:
                    score += 8
            if any(t in complaint_lower for t in ["2pm", "2 pm", "afternoon"]):
                if 13 <= txn_dt.hour <= 15:
                    score += 8
        except Exception:
            pass

    return score


def detect_duplicate_transactions(transactions: list[dict]) -> Optional[dict]:
    """
    Detect if two transactions look like duplicates:
    - Same amount
    - Same counterparty
    - Within 60 seconds of each other
    """
    if len(transactions) < 2:
        return None

    for i in range(len(transactions)):
        for j in range(i + 1, len(transactions)):
            t1 = transactions[i]
            t2 = transactions[j]

            if (
                t1.get("amount") == t2.get("amount")
                and t1.get("counterparty") == t2.get("counterparty")
                and t1.get("type") == t2.get("type")
            ):
                try:
                    dt1 = datetime.fromisoformat(t1["timestamp"].replace("Z", "+00:00"))
                    dt2 = datetime.fromisoformat(t2["timestamp"].replace("Z", "+00:00"))
                    diff_secs = abs((dt1 - dt2).total_seconds())
                    if diff_secs <= 120:  # Within 2 minutes
                        # Return the LATER one as the duplicate
                        later = t2 if dt2 > dt1 else t1
                        return {
                            "duplicate_txn_id": later["transaction_id"],
                            "original_txn_id": t1["transaction_id"] if later == t2 else t2["transaction_id"],
                            "diff_seconds": diff_secs,
                        }
                except Exception:
                    pass

    return None


def detect_established_recipient(transactions: list[dict], target_counterparty: str) -> int:
    """Count how many prior transactions went to the same counterparty."""
    if not target_counterparty:
        return 0
    return sum(
        1 for t in transactions if t.get("counterparty") == target_counterparty
    )


def pre_analyze(request: AnalyzeTicketRequest) -> dict:
    """
    Run rule-based pre-analysis on the ticket.
    Returns structured hints for the LLM prompt.
    """
    complaint = request.complaint
    complaint_lower = complaint.lower()
    transactions = [t.model_dump() for t in (request.transaction_history or [])]
    user_type = (request.user_type or "customer").value if hasattr(request.user_type, 'value') else (request.user_type or "customer")

    analysis = {
        "best_match_txn": None,
        "match_score": 0,
        "is_duplicate_pattern": False,
        "duplicate_txn_ids": None,
        "is_established_recipient": False,
        "recipient_count": 0,
        "has_pending_transactions": False,
        "pending_txn_ids": [],
        "extracted_amount": None,
        "phishing_signals": [],
        "case_type_hint": None,
        "is_ambiguous_match": False,
        "ambiguous_txn_ids": [],
    }

    # Detect phishing
    phishing_signals = detect_phishing_signals(complaint)
    if phishing_signals:
        analysis["phishing_signals"] = phishing_signals
        analysis["case_type_hint"] = "phishing_or_social_engineering"
        return analysis  # Skip transaction analysis for phishing

    # Extract amounts
    amounts = extract_amounts_from_complaint(complaint)
    if amounts:
        analysis["extracted_amount"] = amounts[0]  # Most likely amount

    # Case type hint
    analysis["case_type_hint"] = detect_case_type_hint(complaint, user_type)

    if not transactions:
        return analysis

    # Find pending transactions
    pending = [t for t in transactions if t.get("status") == "pending"]
    if pending:
        analysis["has_pending_transactions"] = True
        analysis["pending_txn_ids"] = [t["transaction_id"] for t in pending]

    # Detect duplicates
    dup = detect_duplicate_transactions(transactions)
    if dup:
        analysis["is_duplicate_pattern"] = True
        analysis["duplicate_txn_ids"] = [dup["duplicate_txn_id"], dup["original_txn_id"]]

    # Detect ambiguous matches: multiple transactions of the same amount + type to
    # DIFFERENT counterparties. Cannot tell which one the complaint refers to.
    if amounts and not analysis["is_duplicate_pattern"]:
        primary_amt = amounts[0]
        amount_matches = [
            t for t in transactions
            if abs(t.get("amount", 0) - primary_amt) < 1
        ]
        distinct_parties = {t.get("counterparty") for t in amount_matches}
        if len(amount_matches) >= 2 and len(distinct_parties) >= 2:
            analysis["is_ambiguous_match"] = True
            analysis["ambiguous_txn_ids"] = [t["transaction_id"] for t in amount_matches]

    # Score each transaction
    best_score = 0
    best_txn = None
    for txn in transactions:
        score = score_transaction_match(txn, amounts, complaint_lower, analysis["case_type_hint"])
        if score > best_score:
            best_score = score
            best_txn = txn

    # When matches are ambiguous, do NOT anchor the model to a single transaction.
    if analysis["is_ambiguous_match"]:
        return analysis

    if best_txn and best_score >= 30:
        analysis["best_match_txn"] = best_txn["transaction_id"]
        analysis["match_score"] = best_score

        # Check established recipient pattern
        counterparty = best_txn.get("counterparty", "")
        if counterparty:
            count = detect_established_recipient(transactions, counterparty)
            if count > 1:
                analysis["is_established_recipient"] = True
                analysis["recipient_count"] = count

    return analysis


# ─── Phase 2: LLM Analysis ────────────────────────────────────────────────────

def call_llm(
    client: Groq,
    request: AnalyzeTicketRequest,
    pre_analysis: dict,
) -> LLMTicketAnalysis:
    """
    Call Groq LLM and return structured ticket analysis.

    Uses a two-model strategy:
    1. Primary: qwen/qwen3.6-27b (as required) — raw JSON output, parses thinking tags
    2. Fallback: meta-llama/llama-4-scout-17b-16e-instruct — supports json_schema structured output
    """

    language = (request.language or Language.EN).value if hasattr(request.language, 'value') else (request.language or "en")
    channel = (request.channel or "in_app_chat").value if hasattr(request.channel, 'value') else (request.channel or "in_app_chat")
    user_type = (request.user_type or "customer").value if hasattr(request.user_type, 'value') else (request.user_type or "customer")

    txn_history_raw = [t.model_dump() for t in (request.transaction_history or [])]

    user_prompt = build_user_prompt(
        ticket_id=request.ticket_id,
        complaint=request.complaint,
        language=language,
        channel=channel,
        user_type=user_type,
        campaign_context=request.campaign_context,
        transaction_history=txn_history_raw,
        pre_analysis=pre_analysis,
        metadata=request.metadata,
    )

    # ── Attempt 1: qwen/qwen3.6-27b (primary model, no response_format) ──
    try:
        # max_retries is a client-level option in the groq SDK, not a create() kwarg.
        # reasoning_effort="none" disables qwen's <think> block — otherwise the
        # reasoning trace overruns max_tokens and the JSON is never emitted (truncated).
        # It also cuts latency from ~15s to ~1s.
        response = client.with_options(max_retries=0, timeout=15).chat.completions.create(
            model="qwen/qwen3.6-27b",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.1,
            max_tokens=1024,
            reasoning_effort="none",
        )
        raw_content = response.choices[0].message.content or ""

        # Strip thinking tags (qwen reasoning models output <think>...</think> before JSON)
        raw_content = re.sub(r"<think>.*?</think>", "", raw_content, flags=re.DOTALL).strip()

        # Extract JSON from the response (handle markdown code blocks)
        raw_content = re.sub(r"^```(?:json)?\s*", "", raw_content, flags=re.MULTILINE).strip()
        raw_content = re.sub(r"```\s*$", "", raw_content, flags=re.MULTILINE).strip()

        # Find JSON object in the content
        json_match = re.search(r"\{.*\}", raw_content, re.DOTALL)
        if json_match:
            raw_json = json.loads(json_match.group())
            # qwen (no response_format) sometimes omits non-critical keys.
            # Backfill safe defaults so a near-miss validates instead of being discarded.
            raw_json.setdefault("relevant_transaction_id", None)
            raw_json.setdefault("recommended_next_action", "Review this ticket and proceed per standard SLA.")
            raw_json.setdefault("confidence", 0.6)
            raw_json.setdefault("reason_codes", ["llm_classification"])
            if not raw_json.get("reason_codes"):
                raw_json["reason_codes"] = ["llm_classification"]
            result = LLMTicketAnalysis.model_validate(raw_json)
            logger.info("qwen/qwen3.6-27b returned valid JSON for %s", request.ticket_id)
            return result
        else:
            raise ValueError(f"No JSON object found in qwen response: {raw_content[:200]}")

    except Exception as e:
        logger.warning("qwen/qwen3.6-27b failed for %s: %s — trying structured fallback", request.ticket_id, type(e).__name__)

    # ── Attempt 2: llama-4-scout with json_schema (structured output) ──
    try:
        response2 = client.with_options(max_retries=1, timeout=20).chat.completions.create(
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "ticket_analysis",
                    "schema": LLMTicketAnalysis.model_json_schema(),
                },
            },
            temperature=0.1,
            max_tokens=1024,
        )
        raw_content2 = response2.choices[0].message.content or "{}"
        raw_json2 = json.loads(raw_content2)
        result2 = LLMTicketAnalysis.model_validate(raw_json2)
        logger.info("llama-4-scout returned valid JSON for %s", request.ticket_id)
        return result2

    except Exception as e2:
        logger.error("Both LLM models failed for %s: %s", request.ticket_id, e2)
        raise RuntimeError(f"All LLM attempts failed: {e2}") from e2


# ─── Fallback Rule-Based Analysis ─────────────────────────────────────────────

def rule_based_fallback(
    request: AnalyzeTicketRequest,
    pre_analysis: dict,
) -> AnalyzeTicketResponse:
    """
    Pure rule-based fallback if LLM fails completely.
    Guarantees valid output structure and safe replies.
    """
    language = (request.language or Language.EN).value if hasattr(request.language, 'value') else (request.language or "en")
    transactions = request.transaction_history or []

    case_type_str = pre_analysis.get("case_type_hint") or "other"
    relevant_txn = pre_analysis.get("best_match_txn")
    phishing = bool(pre_analysis.get("phishing_signals"))

    if phishing:
        return AnalyzeTicketResponse(
            ticket_id=request.ticket_id,
            relevant_transaction_id=None,
            evidence_verdict=EvidenceVerdict.INSUFFICIENT_DATA,
            case_type=CaseType.PHISHING_OR_SOCIAL_ENGINEERING,
            severity=Severity.CRITICAL,
            department=Department.FRAUD_RISK,
            agent_summary="Customer reports a potential phishing or social engineering attempt. Requires immediate fraud team review.",
            recommended_next_action="Escalate to fraud_risk team immediately. Log reported number/details for fraud pattern analysis.",
            customer_reply=get_safe_fallback_reply("", "phishing_or_social_engineering", language),
            human_review_required=True,
            confidence=0.85,
            reason_codes=["phishing_detected", "fraud_risk_escalation"],
        )

    # Generic fallback
    safe_case = case_type_str if case_type_str in [e.value for e in CaseType] else "other"
    return AnalyzeTicketResponse(
        ticket_id=request.ticket_id,
        relevant_transaction_id=relevant_txn,
        evidence_verdict=EvidenceVerdict.INSUFFICIENT_DATA,
        case_type=CaseType(safe_case),
        severity=Severity.MEDIUM,
        department=Department.CUSTOMER_SUPPORT,
        agent_summary="Customer complaint received. Automated analysis encountered an issue. Manual review recommended.",
        recommended_next_action="Review this ticket manually and categorize appropriately.",
        customer_reply=get_safe_fallback_reply("", safe_case, language, relevant_txn),
        human_review_required=True,
        confidence=0.4,
        reason_codes=["fallback_analysis", "manual_review_required"],
    )


# ─── Main Analyzer Entry Point ─────────────────────────────────────────────────

async def analyze_ticket(request: AnalyzeTicketRequest) -> AnalyzeTicketResponse:
    """
    Full analysis pipeline.
    1. Pre-analyze with rule-based engine
    2. Call LLM with context
    3. Validate and repair safety
    4. Return structured response
    """
    language = (request.language or Language.EN).value if hasattr(request.language, 'value') else (request.language or "en")

    # Phase 1: Rule-based pre-analysis
    try:
        pre_analysis = pre_analyze(request)
        logger.info(
            "Pre-analysis complete for %s: case_hint=%s, best_match=%s",
            request.ticket_id,
            pre_analysis.get("case_type_hint"),
            pre_analysis.get("best_match_txn"),
        )
    except Exception as e:
        logger.error("Pre-analysis failed for %s: %s", request.ticket_id, e)
        pre_analysis = {}

    # Phase 2: LLM analysis
    try:
        client = get_groq_client()
        llm_result = call_llm(client, request, pre_analysis)
        logger.info(
            "LLM analysis complete for %s: %s / %s / %s",
            request.ticket_id,
            llm_result.case_type,
            llm_result.evidence_verdict,
            llm_result.department,
        )
    except Exception as e:
        logger.error("LLM call failed for %s: %s", request.ticket_id, e, exc_info=True)
        return rule_based_fallback(request, pre_analysis)

    # Phase 3: Safety validation & repair
    safe_reply, violations = validate_and_repair_reply(
        customer_reply=llm_result.customer_reply,
        case_type=llm_result.case_type,
        language=language,
        relevant_txn_id=llm_result.relevant_transaction_id,
    )

    if violations:
        logger.warning(
            "Safety violations found in reply for %s: %s — reply replaced with safe fallback",
            request.ticket_id,
            [v["type"] for v in violations],
        )

    # Phase 4: Build final response
    try:
        return AnalyzeTicketResponse(
            ticket_id=request.ticket_id,
            relevant_transaction_id=llm_result.relevant_transaction_id,
            evidence_verdict=EvidenceVerdict(llm_result.evidence_verdict),
            case_type=CaseType(llm_result.case_type),
            severity=Severity(llm_result.severity),
            department=Department(llm_result.department),
            agent_summary=llm_result.agent_summary,
            recommended_next_action=llm_result.recommended_next_action,
            customer_reply=safe_reply,
            human_review_required=llm_result.human_review_required,
            confidence=llm_result.confidence,
            reason_codes=llm_result.reason_codes,
        )
    except (ValidationError, ValueError) as e:
        logger.error("Response validation failed for %s: %s", request.ticket_id, e)
        return rule_based_fallback(request, pre_analysis)
