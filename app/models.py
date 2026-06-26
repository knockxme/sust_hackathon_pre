"""
Pydantic models for QueueStorm Investigator API.
Matches the exact schema defined in the problem statement.
"""

from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Literal
from enum import Enum


# ─── Enums ────────────────────────────────────────────────────────────────────

class Language(str, Enum):
    EN = "en"
    BN = "bn"
    MIXED = "mixed"


class Channel(str, Enum):
    IN_APP_CHAT = "in_app_chat"
    CALL_CENTER = "call_center"
    EMAIL = "email"
    MERCHANT_PORTAL = "merchant_portal"
    FIELD_AGENT = "field_agent"


class UserType(str, Enum):
    CUSTOMER = "customer"
    MERCHANT = "merchant"
    AGENT = "agent"
    UNKNOWN = "unknown"


class TransactionType(str, Enum):
    TRANSFER = "transfer"
    PAYMENT = "payment"
    CASH_IN = "cash_in"
    CASH_OUT = "cash_out"
    SETTLEMENT = "settlement"
    REFUND = "refund"


class TransactionStatus(str, Enum):
    COMPLETED = "completed"
    FAILED = "failed"
    PENDING = "pending"
    REVERSED = "reversed"


class EvidenceVerdict(str, Enum):
    CONSISTENT = "consistent"
    INCONSISTENT = "inconsistent"
    INSUFFICIENT_DATA = "insufficient_data"


class CaseType(str, Enum):
    WRONG_TRANSFER = "wrong_transfer"
    PAYMENT_FAILED = "payment_failed"
    REFUND_REQUEST = "refund_request"
    DUPLICATE_PAYMENT = "duplicate_payment"
    MERCHANT_SETTLEMENT_DELAY = "merchant_settlement_delay"
    AGENT_CASH_IN_ISSUE = "agent_cash_in_issue"
    PHISHING_OR_SOCIAL_ENGINEERING = "phishing_or_social_engineering"
    OTHER = "other"


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Department(str, Enum):
    CUSTOMER_SUPPORT = "customer_support"
    DISPUTE_RESOLUTION = "dispute_resolution"
    PAYMENTS_OPS = "payments_ops"
    MERCHANT_OPERATIONS = "merchant_operations"
    AGENT_OPERATIONS = "agent_operations"
    FRAUD_RISK = "fraud_risk"


# ─── Request Schema ────────────────────────────────────────────────────────────

class TransactionEntry(BaseModel):
    transaction_id: str
    timestamp: str  # ISO 8601
    type: TransactionType
    amount: float
    counterparty: str
    status: TransactionStatus


class AnalyzeTicketRequest(BaseModel):
    ticket_id: str = Field(..., min_length=1)
    complaint: str = Field(..., min_length=1)
    language: Optional[Language] = None
    channel: Optional[Channel] = None
    user_type: Optional[UserType] = None
    campaign_context: Optional[str] = None
    transaction_history: Optional[List[TransactionEntry]] = Field(default_factory=list)
    metadata: Optional[dict] = None

    @field_validator("complaint")
    @classmethod
    def complaint_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("complaint cannot be blank")
        return v


# ─── Response Schema ───────────────────────────────────────────────────────────

class AnalyzeTicketResponse(BaseModel):
    ticket_id: str
    relevant_transaction_id: Optional[str] = None
    evidence_verdict: EvidenceVerdict
    case_type: CaseType
    severity: Severity
    department: Department
    agent_summary: str
    recommended_next_action: str
    customer_reply: str
    human_review_required: bool
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    reason_codes: Optional[List[str]] = None


# ─── LLM Structured Output Schema ─────────────────────────────────────────────

class LLMTicketAnalysis(BaseModel):
    """Schema passed to Groq structured output (json_schema mode)."""

    relevant_transaction_id: Optional[str] = Field(
        None,
        description="The transaction_id that best matches the complaint, or null if no match."
    )
    evidence_verdict: Literal["consistent", "inconsistent", "insufficient_data"] = Field(
        ...,
        description=(
            "consistent: complaint details align with transaction evidence. "
            "inconsistent: evidence contradicts the complaint. "
            "insufficient_data: cannot determine from available info."
        )
    )
    case_type: Literal[
        "wrong_transfer",
        "payment_failed",
        "refund_request",
        "duplicate_payment",
        "merchant_settlement_delay",
        "agent_cash_in_issue",
        "phishing_or_social_engineering",
        "other"
    ]
    severity: Literal["low", "medium", "high", "critical"]
    department: Literal[
        "customer_support",
        "dispute_resolution",
        "payments_ops",
        "merchant_operations",
        "agent_operations",
        "fraud_risk"
    ]
    agent_summary: str = Field(
        ...,
        description="Concise 1-2 sentence agent-ready summary including transaction ID if known."
    )
    recommended_next_action: str = Field(
        ...,
        description="Concrete operational next step for the agent team."
    )
    customer_reply: str = Field(
        ...,
        description=(
            "Safe, professional reply to the customer. "
            "MUST include: 'Please do not share your PIN or OTP with anyone.' "
            "MUST NOT: ask for PIN/OTP/password/card details, "
            "promise a refund/reversal, or direct to unofficial third parties. "
            "If a refund might be applicable, say: 'any eligible amount will be returned through official channels'. "
            "Reply in the same language as the complaint (Bangla if complaint is in Bangla)."
        )
    )
    human_review_required: bool = Field(
        ...,
        description="True for disputes, suspicious cases, high-value transactions, or ambiguous situations."
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence score from 0.0 to 1.0 for this classification."
    )
    reason_codes: List[str] = Field(
        ...,
        description="Short reason labels (2-5 items) supporting the classification decision."
    )


# ─── Health Response ───────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str = "ok"


# ─── Error Response ────────────────────────────────────────────────────────────

class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None
