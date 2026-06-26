from __future__ import annotations
"""
Safety guardrail layer for QueueStorm Investigator.

Two-layer protection:
  Layer 1: System prompt instructions (in prompts.py)
  Layer 2: Post-processing validation here (catches any LLM slippage)

Penalty structure we're protecting against:
  -15 pts: Asks for PIN, OTP, password, full card number
  -10 pts: Confirms refund/reversal/recovery without authority
  -10 pts: Directs customer to suspicious 3rd parties
  Disqualification: 2+ critical safety violations
"""

import re
from typing import Optional


# ─── Banned Patterns ───────────────────────────────────────────────────────────

# Patterns that constitute credential-asking violations (-15 pts each)
# Uses negative lookbehind to avoid flagging safe negations like:
#   "do not share your PIN", "never ask for your OTP", "don't share your password"
_NEG = r"(?<!do not )(?<!don't )(?<!never )(?<!not )(?<!please do not )"
CREDENTIAL_REQUEST_PATTERNS = [
    # Direct asks (must NOT be preceded by negation words)
    _NEG + r"(?<!\bdo )(?<!\bnot )\bshare\s+your\s+(pin|otp|password|card\s+number)\b",
    r"\bprovide\s+your\s+(pin|otp|password|card\s+number)\b",
    r"\benter\s+your\s+(pin|otp|password|card\s+number)\b",
    r"\bsend\s+us\s+your\s+(pin|otp|password)\b",
    r"\bgive\s+us\s+your\s+(pin|otp|password)\b",
    r"\bwhat\s+is\s+your\s+(pin|otp|password)\b",
    r"\bverify\s+your\s+(pin|otp|password)\b",
    # Implicit asks
    r"\bplease\s+confirm\s+your\s+(pin|otp)\b",
    r"\bcan\s+you\s+share\s+your\s+(pin|otp)\b",
]

# Patterns that constitute unauthorized refund promises (-10 pts each)
UNAUTHORIZED_REFUND_PATTERNS = [
    r"\bwe\s+will\s+refund\s+you\b",
    r"\byour\s+money\s+will\s+be\s+returned\b",
    r"\bwe\s+will\s+return\s+your\s+(money|funds|amount|payment)\b",
    r"\byou\s+will\s+receive\s+a\s+refund\b",
    r"\bwe\s+guarantee\s+a\s+refund\b",
    r"\brefund\s+will\s+be\s+processed\b",
    r"\bwe\s+will\s+reverse\s+the\s+transaction\b",
    r"\bthe\s+transaction\s+will\s+be\s+reversed\b",
    r"\bwe\s+will\s+recover\s+your\s+(money|funds)\b",
    r"\byour\s+account\s+will\s+be\s+unblocked\b",
]

# Patterns that constitute third-party direction violations (-10 pts each)
THIRD_PARTY_PATTERNS = [
    r"\bcontact\s+google\b",
    r"\bcontact\s+facebook\b",
    r"\bcontact\s+police\b",
    r"\bgo\s+to\s+a\s+different\s+(website|app|service)\b",
    r"\bvisit\s+[a-zA-Z0-9]+\.(com|net|org)\b",
]

# Required safety phrase (must be present in every customer_reply)
REQUIRED_SAFETY_PHRASES = [
    # English variants
    "do not share your pin",
    "don't share your pin",
    "do not share your otp",
    "don't share your otp",
    "please do not share",
    # Bangla variants
    "পিন বা ওটিপি শেয়ার করবেন না",
    "পিন বা ওটিপি",
    "পিন শেয়ার",
]

# Safe refund language (acceptable alternatives)
SAFE_REFUND_PHRASES = [
    "any eligible amount will be returned",
    "eligible amount will be returned",
    "will be returned through official channels",
]


def check_reply_safety(customer_reply: str) -> dict:
    """
    Validate customer_reply against all safety rules.
    Returns a dict with violations found and whether repair is needed.
    """
    reply_lower = customer_reply.lower()
    violations = []

    # ── Credential request check ──
    # First, mask safe negation phrases so they don't trigger false positives.
    # "Please do not share your PIN or OTP with anyone" is SAFE — it's a warning.
    # We remove these negation clauses before scanning for actual credential asks.
    SAFE_NEGATION_SNIPPETS = [
        "do not share your pin",
        "do not share your otp",
        "don't share your pin",
        "don't share your otp",
        "never share your pin",
        "never share your otp",
        "not share your pin",
        "not share your otp",
        "we never ask for your pin",
        "we never ask for your otp",
        "we never ask for your password",
        "never ask for your pin",
        "never ask for your otp",
        "পিন বা ওটিপি শেয়ার করবেন না",
        "পিন শেয়ার",
    ]
    sanitized = reply_lower
    for safe_snippet in SAFE_NEGATION_SNIPPETS:
        sanitized = sanitized.replace(safe_snippet, "[SAFE_REMINDER]")

    # Now scan the sanitized text for actual credential requests
    for pattern in CREDENTIAL_REQUEST_PATTERNS:
        if re.search(pattern, sanitized, re.IGNORECASE):
            violations.append({
                "type": "credential_request",
                "severity": "critical",
                "penalty": -15,
                "pattern": pattern,
            })

    # Check for unauthorized refund promises
    # (only flag if it's a promise, not if safe language is used)
    has_safe_refund = any(p in reply_lower for p in SAFE_REFUND_PHRASES)
    if not has_safe_refund:
        for pattern in UNAUTHORIZED_REFUND_PATTERNS:
            if re.search(pattern, reply_lower, re.IGNORECASE):
                violations.append({
                    "type": "unauthorized_refund_promise",
                    "severity": "critical",
                    "penalty": -10,
                    "pattern": pattern,
                })

    # Check for third-party direction
    for pattern in THIRD_PARTY_PATTERNS:
        if re.search(pattern, reply_lower, re.IGNORECASE):
            violations.append({
                "type": "third_party_direction",
                "severity": "critical",
                "penalty": -10,
                "pattern": pattern,
            })

    return {
        "is_safe": len(violations) == 0,
        "violations": violations,
        "violation_count": len(violations),
    }


def ensure_safety_reminder(customer_reply: str, language: str = "en") -> str:
    """
    Ensure the reply contains the required safety reminder.
    Appends it if missing.
    """
    reply_lower = customer_reply.lower()
    has_reminder = any(phrase in reply_lower for phrase in REQUIRED_SAFETY_PHRASES)

    if not has_reminder:
        if language == "bn":
            customer_reply = customer_reply.rstrip() + " অনুগ্রহ করে কারো সাথে আপনার পিন বা ওটিপি শেয়ার করবেন না।"
        else:
            customer_reply = customer_reply.rstrip() + " Please do not share your PIN or OTP with anyone."

    return customer_reply


def get_safe_fallback_reply(
    ticket_id: str,
    case_type: str,
    language: str = "en",
    relevant_txn_id: Optional[str] = None,
) -> str:
    """
    Generate a guaranteed-safe fallback reply when LLM output fails safety check.
    """
    txn_ref = f" regarding transaction {relevant_txn_id}" if relevant_txn_id else ""

    if language == "bn":
        # Safe Bangla fallback
        if relevant_txn_id:
            return (
                f"আপনার অভিযোগ{txn_ref} সম্পর্কে আমরা অবগত হয়েছি। "
                "আমাদের দল দ্রুত এটি পর্যালোচনা করবে এবং অফিসিয়াল চ্যানেলের মাধ্যমে "
                "আপনাকে জানাবে। অনুগ্রহ করে কারো সাথে আপনার পিন বা ওটিপি শেয়ার করবেন না।"
            )
        return (
            "আপনার অভিযোগের জন্য ধন্যবাদ। আমাদের দল দ্রুত এটি পর্যালোচনা করবে "
            "এবং অফিসিয়াল চ্যানেলের মাধ্যমে আপনাকে জানাবে। "
            "অনুগ্রহ করে কারো সাথে আপনার পিন বা ওটিপি শেয়ার করবেন না।"
        )

    # Fallback replies by case type (English)
    fallbacks = {
        "phishing_or_social_engineering": (
            "Thank you for reaching out before sharing any information. "
            "We never ask for your PIN, OTP, or password under any circumstances. "
            "Please do not share these with anyone, even if they claim to be from us. "
            "Our fraud team has been notified and will review this incident. "
            "Please do not share your PIN or OTP with anyone."
        ),
        "wrong_transfer": (
            f"We have noted your concern{txn_ref}. "
            "Our dispute team will review the case and contact you through official support channels. "
            "Any eligible amount will be returned through official channels. "
            "Please do not share your PIN or OTP with anyone."
        ),
        "payment_failed": (
            f"We have noted that{txn_ref} may have caused an unexpected issue. "
            "Our payments team will review the case and any eligible amount will be returned through official channels. "
            "Please do not share your PIN or OTP with anyone."
        ),
        "duplicate_payment": (
            f"We have noted a possible duplicate payment{txn_ref}. "
            "Our payments team will verify with the relevant party and "
            "any eligible amount will be returned through official channels. "
            "Please do not share your PIN or OTP with anyone."
        ),
        "refund_request": (
            f"Thank you for reaching out{txn_ref}. "
            "We have noted your request. Our support team will review the case "
            "and guide you on the appropriate next steps through official channels. "
            "Please do not share your PIN or OTP with anyone."
        ),
        "merchant_settlement_delay": (
            f"We have noted your concern{txn_ref}. "
            "Our merchant operations team will check the settlement status "
            "and update you through official channels. "
            "Please do not share your PIN or OTP with anyone."
        ),
        "agent_cash_in_issue": (
            f"We have noted your concern{txn_ref}. "
            "Our agent operations team will verify the transaction status "
            "and resolve it within the standard SLA. "
            "Please do not share your PIN or OTP with anyone."
        ),
    }

    return fallbacks.get(
        case_type,
        (
            f"Thank you for reaching out{txn_ref}. "
            "We have noted your concern and our support team will review it "
            "and contact you through official support channels. "
            "Please do not share your PIN or OTP with anyone."
        ),
    )


def validate_and_repair_reply(
    customer_reply: str,
    case_type: str,
    language: str = "en",
    relevant_txn_id: Optional[str] = None,
) -> tuple[str, list]:
    """
    Full safety validation pipeline.
    Returns (safe_reply, list_of_violations_found).
    """
    safety_check = check_reply_safety(customer_reply)

    if not safety_check["is_safe"]:
        # Replace with guaranteed-safe fallback
        safe_reply = get_safe_fallback_reply(
            ticket_id="",
            case_type=case_type,
            language=language,
            relevant_txn_id=relevant_txn_id,
        )
        return safe_reply, safety_check["violations"]

    # Reply is safe, just ensure it has the required reminder
    safe_reply = ensure_safety_reminder(customer_reply, language)
    return safe_reply, []
