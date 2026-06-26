"""Test qwen model with a fuller prompt for json_object."""
import os
from dotenv import load_dotenv
load_dotenv()
from groq import Groq

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# Test json_object with a more complete prompt
try:
    r = client.chat.completions.create(
        model="qwen/qwen3.6-27b",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a ticket classifier. You MUST output only valid JSON. "
                    "No thinking tags. No preamble. No markdown. Just the JSON object."
                )
            },
            {
                "role": "user",
                "content": (
                    "Classify this ticket: Customer says they sent 5000 taka to wrong number at 2pm today. "
                    "Transaction TXN-9101 exists: transfer, 5000 BDT, 14:08, completed. "
                    "Output JSON with fields: relevant_transaction_id, evidence_verdict (consistent/inconsistent/insufficient_data), "
                    "case_type (wrong_transfer/payment_failed/other), severity (low/medium/high/critical), "
                    "department (customer_support/dispute_resolution/payments_ops/fraud_risk), "
                    "agent_summary, customer_reply, human_review_required (true/false), confidence (0-1)"
                )
            }
        ],
        response_format={"type": "json_object"},
        temperature=0.1,
        max_tokens=600
    )
    print("SUCCESS:", r.choices[0].message.content[:500])
except Exception as e:
    print("FAILED:", e)

# Also test without response_format
print("\n--- Testing without response_format ---")
try:
    r2 = client.chat.completions.create(
        model="qwen/qwen3.6-27b",
        messages=[
            {
                "role": "system",
                "content": "You are a ticket classifier. Output ONLY raw JSON. No thinking. No markdown."
            },
            {
                "role": "user",
                "content": (
                    "Return JSON with: relevant_transaction_id=TXN-9101, "
                    "evidence_verdict=consistent, case_type=wrong_transfer, "
                    "severity=high, department=dispute_resolution, "
                    "agent_summary=test, customer_reply=test, human_review_required=true, "
                    "confidence=0.9, reason_codes=[wrong_transfer]"
                )
            }
        ],
        temperature=0.1,
        max_tokens=300
    )
    print("Raw output:", r2.choices[0].message.content[:400])
except Exception as e:
    print("FAILED:", e)
